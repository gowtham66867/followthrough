"""Single-process durable jobs; startup requeues interrupted work."""
from __future__ import annotations

import json
import threading
import uuid
import httpx
from pydantic import ValidationError
from . import demo, domain
from .models import Nebius, validate_evidence
from .schemas import Message
from .store import Conflict, event, now


class Jobs:
    def __init__(self, store, config):
        self.store, self.config = store, config
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.worker = None

    def start(self):
        with self.store.transaction() as connection:
            connection.execute("UPDATE jobs SET status='queued',updated_at=? WHERE status='running'", (now(),))
        self.worker = threading.Thread(target=self.loop, name='followthrough-worker', daemon=True)
        self.worker.start()

    def stop(self):
        self.stopping.set()
        self.wake.set()
        if self.worker:
            self.worker.join(timeout=3)

    def enqueue(self, kind, mode, payload, key):
        with self.store.transaction() as connection:
            previous = connection.execute('SELECT * FROM jobs WHERE command_key=?', (key,)).fetchone()
            if previous:
                if previous['payload_json'] != json.dumps(payload, sort_keys=True) or previous['mode'] != mode or previous['kind'] != kind:
                    raise Conflict('Idempotency key was reused for a different command')
                return dict(previous)
            job_id = uuid.uuid4().hex
            connection.execute('INSERT INTO jobs(id,command_key,kind,mode,payload_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                               (job_id, key, kind, mode, json.dumps(payload, sort_keys=True), now(), now()))
            event(connection, 'job_queued', {'kind': kind, 'mode': mode}, job_id=job_id)
        self.wake.set()
        return self.get(job_id)

    def get(self, job_id):
        rows = self.store.query('SELECT * FROM jobs WHERE id=?', (job_id,))
        if not rows:
            raise LookupError('Job not found')
        return rows[0]

    def retry(self, job_id):
        with self.store.transaction() as connection:
            row = connection.execute('SELECT status FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                raise LookupError('Job not found')
            if row[0] != 'failed':
                raise Conflict('Only failed jobs can be retried')
            connection.execute("UPDATE jobs SET status='queued',error=NULL,updated_at=? WHERE id=?", (now(), job_id))
            event(connection, 'job_retried', {}, job_id=job_id)
        self.wake.set()
        return self.get(job_id)

    def cancel(self, job_id):
        with self.store.transaction() as connection:
            row = connection.execute('SELECT status FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                raise LookupError('Job not found')
            if row[0] != 'queued':
                raise Conflict('Only queued jobs can be cancelled; running work finishes atomically')
            connection.execute("UPDATE jobs SET status='cancelled',updated_at=? WHERE id=?", (now(), job_id))
            event(connection, 'job_cancelled', {}, job_id=job_id)
        return self.get(job_id)

    def stage(self, job_id, name, detail=None):
        with self.store.transaction() as connection:
            event(connection, name, detail or {}, job_id=job_id)

    def loop(self):
        while not self.stopping.is_set():
            with self.store.transaction() as connection:
                row = connection.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
                if row:
                    connection.execute("UPDATE jobs SET status='running',attempts=attempts+1,updated_at=? WHERE id=?", (now(), row['id']))
            if row:
                self.execute(dict(row))
            else:
                self.wake.wait(timeout=2)
                self.wake.clear()

    def execute(self, job):
        job_id = job['id']
        try:
            payload = json.loads(job['payload_json'])
            if job['kind'] == 'import':
                self.stage(job_id, 'normalizing', {'mode': job['mode']})
                messages = [Message.model_validate(m) for m in payload['messages']]
                ids = [m.id for m in messages]
                if len(ids) != len(set(ids)):
                    raise ValueError('Each imported message must have a unique ID')
                fresh = []
                for message in messages:
                    prior = self.store.query('SELECT content_hash FROM messages WHERE id=?', (message.id,))
                    if prior:
                        if prior[0]['content_hash'] != domain.digest(message.model_dump(mode='json')):
                            raise Conflict('Source ID reused with changed content; original source was preserved')
                    else:
                        fresh.append(message)
                self.stage(job_id, 'extracting', {'new_messages': len(fresh)})
                if not fresh:
                    from .schemas import Extraction
                    extraction, usage = Extraction(claims=[]), {'mode': job['mode'], 'model': None}
                elif job['mode'] == 'fixture':
                    extraction, usage = demo.extract(fresh), {'mode': 'fixture', 'model': 'fictional fixture interpreter'}
                else:
                    extraction, usage = Nebius(self.config).extract(fresh, self.store.query(
                        "SELECT o.id,o.title,m.thread_id FROM opportunities o JOIN messages m ON m.opportunity_id=o.id WHERE o.mode='live' GROUP BY o.id,m.thread_id"))
                validate_evidence(extraction, fresh)
                self.stage(job_id, 'validating', {'claims': len(extraction.claims)})
                result = domain.apply_extraction(self.store, fresh, extraction, job['mode'], job_id, usage)
            elif job['kind'] == 'draft':
                result = self.draft(job_id, payload, job['mode'])
            else:
                raise ValueError('Unknown job type')
            with self.store.transaction() as connection:
                connection.execute("UPDATE jobs SET status='succeeded',result_json=?,updated_at=? WHERE id=?", (json.dumps(result), now(), job_id))
                event(connection, 'job_succeeded', result, job_id=job_id)
        except Exception as exc:
            # Provider bodies can echo submitted data. Store a bounded public error only.
            error = str(exc)[:400] if isinstance(exc, (ValueError, LookupError)) else 'Processing failed; private source data was not logged. Retry or check server configuration.'
            if isinstance(exc, (ValidationError, json.JSONDecodeError)):
                error = 'Model output did not match the required schema. No changes were applied.'
            if isinstance(exc, httpx.TimeoutException):
                error = 'Provider timed out. Existing work is preserved; retry this job.'
            with self.store.transaction() as connection:
                connection.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?", (error, now(), job_id))
                event(connection, 'job_failed', {'error': error}, job_id=job_id)

    def draft(self, job_id, payload, mode):
        op_id = payload['opportunity_id']
        current = domain.detail(self.store, op_id)
        if current['revision'] != payload['expected_revision']:
            raise Conflict('Package changed while drafting was queued; review and draft again')
        facts = {r['key']: r['value'] for r in self.store.query('SELECT * FROM facts')}
        self.stage(job_id, 'drafting', {'fields': len(current['requirements'])})
        if mode == 'fixture':
            drafts = [{'key': r['requirement_key'], 'answer': facts.get(r['requirement_key'], ''),
                       'fact_keys': [r['requirement_key']] if facts.get(r['requirement_key']) else []}
                      for r in current['requirements']]
            usage = {'mode': 'fixture', 'model': 'fictional fixture drafter'}
        else:
            raw, usage = Nebius(self.config).complete('draft.txt', {'facts': facts, 'fields': current['requirements']})
            drafts = raw.get('drafts')
            if not isinstance(drafts, list):
                raise ValueError('Model response must contain drafts')
        # Conservative grounding: every proposed answer must occur in a cited fact.
        # Unsupported paraphrases remain gaps for a human to write, never auto-confirmed.
        allowed = {r['requirement_key'] for r in current['requirements']}
        with self.store.transaction() as connection:
            domain.require_op(connection, op_id, payload['expected_revision'])
            if current['workflow'] in ('closed', 'cancelled'):
                raise Conflict('Closed opportunities cannot be redrafted')
            answers = current['package']['answers']
            saved = 0
            seen = set()
            for draft in drafts:
                key = draft.get('key')
                if key not in allowed or key in seen:
                    raise ValueError('Draft references an unknown or duplicate field')
                seen.add(key)
                if answers.get(key, {}).get('confirmed'):
                    continue
                answer, refs = draft.get('answer', ''), draft.get('fact_keys', [])
                if not isinstance(answer, str) or not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
                    raise ValueError('Invalid draft schema')
                valid = answer and refs and all(ref in facts for ref in refs) and any(answer in facts[ref] for ref in refs)
                if valid:
                    answers[key] = {'answer': answer, 'confirmed': False, 'fact_keys': refs,
                                    'provenance': 'draft_from_confirmed_facts', 'updated_at': now()}
                    saved += 1
            if saved:
                connection.execute('UPDATE packages SET answers_json=? WHERE opportunity_id=?', (json.dumps(answers), op_id))
                domain.touch(connection, op_id, 'package_drafted', {'fields': saved, **usage})
        return {'drafted': saved, 'opportunity_id': op_id, **usage}
