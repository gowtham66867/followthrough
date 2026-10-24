"""Loopback-only FastAPI application; every private endpoint uses a local session."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import demo, domain
from .gmail import Gmail
from .jobs import Jobs
from .schemas import (ImportRequest, RevisionCommand, AnswerCommand, ReceiptCommand,
                      DeadlineCommand, ChatCommand, FactsCommand)
from .store import Store, Conflict, event, now


class Scenario(BaseModel):
    scenario: str
    command_key: str = Field(min_length=8, max_length=200)


class SelectedGmail(BaseModel):
    message_ids: list[str] = Field(min_length=1, max_length=15)
    command_key: str = Field(min_length=8, max_length=200)


def create_app(directory: Path, config=None, port=8787):
    config = {'model': '', 'timezone': 'Asia/Kolkata',
              'gmail_redirect_uri': f'http://127.0.0.1:{port}/api/gmail/callback', **(config or {})}
    ZoneInfo(config['timezone'])
    store = Store(directory)
    jobs = Jobs(store, config)
    gmail = Gmail(directory, config)
    session = secrets.token_urlsafe(40)
    origins = {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}
    hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
    dist = Path(__file__).parents[1] / 'frontend/dist'

    @asynccontextmanager
    async def lifespan(app):
        jobs.start()
        yield
        jobs.stop()

    app = FastAPI(title='FollowThrough', version='0.4.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.jobs, app.state.config = store, jobs, config
    from .proposal_routes import router as proposal_router
    app.include_router(proposal_router(store, config))

    @app.middleware('http')
    async def local_boundary(request, call_next):
        if request.headers.get('host') not in hosts:
            return JSONResponse({'error': 'This workspace only accepts its loopback host'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin not in origins:
            return JSONResponse({'error': 'Cross-origin access is not allowed'}, status_code=403)
        if request.url.path.startswith('/api/') and request.cookies.get('followthrough_session') != session:
            return JSONResponse({'error': 'Open the local workspace to start a session'}, status_code=401)
        if request.headers.get('content-length', '0').isdigit() and int(request.headers.get('content-length', '0')) > 5_000_000:
            return JSONResponse({'error': 'Request exceeds the 5 MB limit'}, status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({'error': str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def validation_handler(request, exc):
        return JSONResponse({'error': str(exc)[:400]}, status_code=400)

    @app.exception_handler(LookupError)
    async def missing_handler(request, exc):
        return JSONResponse({'error': str(exc)}, status_code=404)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(request, exc):
        # Pydantic's default response includes rejected input, possibly private email.
        return JSONResponse({'error': 'Invalid request', 'fields': [str(e['loc']) for e in exc.errors()]}, status_code=422)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'application': 'FollowThrough', 'deployment': 'local single-owner workspace'}

    @app.get('/api/settings')
    def settings():
        return {'timezone': config['timezone'], 'model': config['model'],
                'nebius_key_configured': bool(os.environ.get('NEBIUS_API_KEY') or os.environ.get('NEBIUS_TOKEN_FACTORY_API_KEY')),
                'gmail': gmail.status(), 'deployment': 'Local only · single owner',
                'data_policy': 'Selected live emails are sent to Nebius. Local history and OAuth tokens are not encrypted at rest.'}

    @app.get('/api/snapshot')
    def snapshot():
        opportunities = [domain.detail(store, op['id']) for op in store.query('SELECT id FROM opportunities ORDER BY created_at DESC')]
        job_rows = store.query('SELECT id,kind,mode,status,error,result_json,attempts,created_at FROM jobs ORDER BY created_at DESC LIMIT 12')
        return {'opportunities': opportunities, 'jobs': job_rows,
                'facts': store.query('SELECT * FROM facts ORDER BY key'), 'settings': settings()}

    @app.post('/api/demo/import')
    def demo_import(body: Scenario):
        messages = demo.messages_for(body.scenario)
        return jobs.enqueue('import', 'fixture', {'messages': [m.model_dump(mode='json') for m in messages]}, body.command_key)

    @app.post('/api/demo/profile')
    def demo_profile():
        # Never seed fictional personal facts into a workspace containing real messages.
        if store.query("SELECT 1 FROM messages WHERE mode='live' LIMIT 1"):
            raise Conflict('Fictional profile is disabled in a workspace containing live email')
        return put_facts(FactsCommand(facts=demo.FACTS), provenance='fictional profile confirmed by user')

    @app.post('/api/imports')
    def imports(body: ImportRequest):
        if store.query("SELECT 1 FROM facts WHERE provenance LIKE 'fictional%' LIMIT 1"):
            raise Conflict('Remove the fictional profile facts before importing live email, or use a separate data directory')
        return jobs.enqueue('import', 'live', {'messages': [m.model_dump(mode='json') for m in body.messages]}, body.command_key)

    @app.get('/api/jobs/{job_id}')
    def job_status(job_id: str):
        job = jobs.get(job_id)
        return {key: value for key, value in job.items() if key != 'payload_json'}

    @app.post('/api/jobs/{job_id}/retry')
    def retry_job(job_id: str):
        return jobs.retry(job_id)

    @app.post('/api/jobs/{job_id}/cancel')
    def cancel_job(job_id: str):
        return jobs.cancel(job_id)

    @app.get('/api/jobs/{job_id}/events')
    async def job_events(job_id: str, request: Request):
        jobs.get(job_id)
        try:
            last = int(request.headers.get('last-event-id', '0'))
        except ValueError:
            last = 0
        async def stream():
            nonlocal last
            for _ in range(120):
                if await request.is_disconnected():
                    break
                for row in store.query('SELECT * FROM events WHERE job_id=? AND id>? ORDER BY id', (job_id, last)):
                    last = row['id']
                    yield f'id: {last}\ndata: {json.dumps(row)}\n\n'
                status = jobs.get(job_id)['status']
                if status in ('succeeded', 'failed', 'cancelled'):
                    yield f'event: complete\ndata: {json.dumps({"status": status})}\n\n'
                    break
                yield ': keepalive\n\n'
                await asyncio.sleep(0.5)
        return StreamingResponse(stream(), media_type='text/event-stream')

    @app.get('/api/obligations/{op_id}')
    def get_obligation(op_id: str):
        return domain.detail(store, op_id)

    @app.patch('/api/obligations/{op_id}/answers/{key}')
    def answer(op_id: str, key: str, body: AnswerCommand):
        return domain.save_answer(store, op_id, key, body.answer, body.expected_revision, confirmed=body.confirm)

    @app.post('/api/obligations/{op_id}/deadline')
    def deadline(op_id: str, body: DeadlineCommand):
        return domain.confirm_deadline(store, op_id, body.source_id, body.expected_revision, body.due_at)

    @app.post('/api/obligations/{op_id}/draft')
    def draft(op_id: str, body: RevisionCommand):
        current = domain.detail(store, op_id)
        if current['revision'] != body.expected_revision:
            raise Conflict('Refresh before drafting')
        return jobs.enqueue('draft', current['mode'], {'opportunity_id': op_id, **body.model_dump()},
                            f'draft:{op_id}:{body.expected_revision}')

    @app.get('/api/obligations/{op_id}/preview')
    def preview(op_id: str):
        return domain.detail(store, op_id)

    @app.post('/api/obligations/{op_id}/approve')
    def approve(op_id: str, body: RevisionCommand):
        return domain.approve(store, op_id, body.expected_revision)

    @app.post('/api/obligations/{op_id}/submitted')
    def submitted(op_id: str, body: RevisionCommand):
        return domain.mark_submitted(store, op_id, body.expected_revision)

    @app.post('/api/obligations/{op_id}/receipt-review')
    def receipt(op_id: str, body: ReceiptCommand):
        return domain.review_receipt(store, op_id, body.receipt_id, body.decision, body.expected_revision)

    @app.get('/api/obligations/{op_id}/export')
    def export(op_id: str):
        current = domain.detail(store, op_id)
        package = current['package']
        if package['approval_revision'] != current['revision'] or package['approval_hash'] != domain.digest(package['answers']):
            raise Conflict('Approve the current package before exporting')
        lines = [current['title'], f'Reviewed package revision {current["revision"]}',
                 'Prepared materials only. External submission is manual.', '']
        for req in current['requirements']:
            answer = package['answers'].get(req['requirement_key'], {}).get('answer', '(not supplied)')
            lines += [req['title'], answer, f'Source: {req["source_id"]}', f'Quoted requirement: {req["quote"]}', '']
        lines += ['Package content SHA-256: ' + package['approval_hash']]
        return Response('\n'.join(lines), media_type='text/plain', headers={'Content-Disposition': 'attachment; filename="followthrough-package.txt"'})

    @app.put('/api/profile')
    def put_facts(body: FactsCommand, provenance='user confirmed'):
        with store.transaction() as connection:
            changed = False
            for key, value in body.facts.items():
                existing = connection.execute('SELECT value FROM facts WHERE key=?', (key,)).fetchone()
                if existing and existing[0] == value:
                    continue
                changed = True
                connection.execute('INSERT INTO facts VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,provenance=excluded.provenance,updated_at=excluded.updated_at',
                                   (key, value, provenance, now()))
            if changed:
                for op in connection.execute("SELECT id FROM opportunities WHERE workflow NOT IN ('closed','cancelled')").fetchall():
                    domain.touch(connection, op[0], 'profile_updated', {'review_required': True})
            event(connection, 'profile_saved', {'keys': list(body.facts)})
        return {'facts': store.query('SELECT * FROM facts')}

    @app.delete('/api/profile')
    def delete_profile():
        with store.transaction() as connection:
            connection.execute('DELETE FROM facts')
            for row in connection.execute("SELECT id FROM opportunities WHERE workflow NOT IN ('closed','cancelled')").fetchall():
                domain.touch(connection, row[0], 'profile_removed_review_needed', {})
            event(connection, 'profile_removed', {})
        return {'ok': True}

    @app.post('/api/obligations/{op_id}/conversation')
    def chat(op_id: str, body: ChatCommand):
        if body.field_key:
            if body.expected_revision is None:
                raise ValueError('A revision is required when saving an answer')
            domain.save_answer(store, op_id, body.field_key, body.message, body.expected_revision)
        current = domain.detail(store, op_id)
        missing = [r for r in current['requirements'] if not current['package']['answers'].get(r['requirement_key'], {}).get('confirmed')]
        if not current['deadline'] or not current['deadline']['selected']:
            reply = 'The deadline still needs your review. Open its source and confirm the applicable date before approving the package.'
        elif missing:
            first = missing[0]
            reply = f'Let’s finish {first["title"].lower()}. Select that field and provide the answer you want to use. I will save your words without inventing missing facts.'
        elif current['workflow'] == 'closed':
            reply = 'A submission receipt has been reviewed and linked. It confirms receipt, not acceptance or an award.'
        else:
            reply = f'Every required field is reviewed. Open the complete preview for revision {current["revision"]}. Approval does not submit anything externally.'
        with store.transaction() as connection:
            for role, text in [('user', body.message), ('assistant', reply)]:
                connection.execute('INSERT INTO conversations(opportunity_id,role,text,created_at) VALUES (?,?,?,?)', (op_id, role, text, now()))
        return {'reply': reply, 'field_key': missing[0]['requirement_key'] if missing else None}

    @app.get('/api/gmail/start')
    def gmail_start():
        return RedirectResponse(gmail.start())

    @app.get('/api/gmail/callback')
    def gmail_callback(code: str = '', state: str = '', error: str = ''):
        if error:
            raise ValueError('Gmail authorization was declined')
        gmail.callback(code, state)
        return RedirectResponse('/?connected=gmail')

    @app.get('/api/gmail/messages')
    def gmail_messages(q: str = 'newer_than:30d hackathon', page_token: str | None = None):
        if len(q) > 1000:
            raise ValueError('Search query is too long')
        return gmail.search(q, page_token)

    @app.post('/api/gmail/import')
    def gmail_import(body: SelectedGmail):
        if store.query("SELECT 1 FROM facts WHERE provenance LIKE 'fictional%' LIMIT 1"):
            raise Conflict('Remove fictional profile facts before importing live Gmail, or use a separate workspace')
        messages = gmail.selected(body.message_ids)
        return imports(ImportRequest(messages=messages, command_key=body.command_key))

    @app.post('/api/gmail/disconnect')
    def gmail_disconnect():
        gmail.disconnect()
        return {'ok': True}

    @app.get('/')
    def index():
        if not (dist / 'index.html').exists():
            response = JSONResponse({'error': 'Build the frontend first: npm --prefix followthrough/frontend run build'}, status_code=503)
        else:
            response = FileResponse(dist / 'index.html')
        response.set_cookie('followthrough_session', session, httponly=True, samesite='lax', max_age=86400)
        return response

    if dist.exists():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')
    return app
