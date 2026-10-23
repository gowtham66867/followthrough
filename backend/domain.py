"""Evidence-linked state transitions. Models cannot call around this boundary."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
from urllib.parse import urlparse
from .store import Conflict, event, now
from .claims import CLAIM_HANDLERS


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def require_op(connection, op_id, revision=None):
    op = connection.execute('SELECT * FROM opportunities WHERE id=?', (op_id,)).fetchone()
    if op is None:
        raise LookupError('Opportunity not found')
    if revision is not None and revision != op['revision']:
        raise Conflict('This view is out of date. Review the current revision and try again.')
    return dict(op)


def touch(connection, op_id, kind, detail, *, reopen_closed=False):
    op = require_op(connection, op_id)
    revision = op['revision'] + 1
    connection.execute("UPDATE opportunities SET revision=?,workflow=CASE WHEN workflow IN ('closed','cancelled','awaiting_receipt') THEN workflow ELSE 'preparing' END WHERE id=?", (revision, op_id))
    connection.execute('UPDATE packages SET revision=?,approval_revision=NULL,approval_hash=NULL WHERE opportunity_id=?', (revision, op_id))
    if reopen_closed and op['workflow'] in ('closed', 'awaiting_receipt'):
        connection.execute("UPDATE opportunities SET workflow='preparing',completion_basis='none' WHERE id=?", (op_id,))
        event(connection, 'completion_needs_fresh_review', {'previous_basis': op['completion_basis']}, op_id)
    event(connection, kind, {**detail, 'revision': revision}, op_id)
    return revision


def apply_extraction(store, messages, extraction, mode, job_id, usage):
    with store.transaction() as connection:
        fresh = set()
        for message in messages:
            payload = message.model_dump(mode='json')
            content_hash = digest(payload)
            previous = connection.execute('SELECT content_hash FROM messages WHERE id=?', (message.id,)).fetchone()
            if previous:
                if previous['content_hash'] != content_hash:
                    raise Conflict('A source ID was reused with changed content; original evidence was preserved')
                continue
            connection.execute('INSERT INTO messages(id,thread_id,subject,sender,received_at,body,content_hash,mode,external_url) VALUES (?,?,?,?,?,?,?,?,?)',
                               (message.id, message.thread_id, message.subject, message.sender,
                                payload['received_at'], message.body, content_hash, mode, message.external_url))
            fresh.add(message.id)
        touched = set()
        for claim in extraction.claims:
            if claim.source_id not in fresh:
                continue
            op_id = mode + '-' + claim.opportunity_id
            previous = connection.execute('SELECT * FROM opportunities WHERE id=?', (op_id,)).fetchone()
            if previous and mode == 'live':
                threads = {r['thread_id'] for r in connection.execute('SELECT thread_id FROM messages WHERE opportunity_id=?', (op_id,))}
                source_thread = connection.execute('SELECT thread_id FROM messages WHERE id=?', (claim.source_id,)).fetchone()[0]
                if threads and source_thread not in threads:
                    raise ValueError('Cross-thread linking requires human review; import this thread as a separate opportunity')
            if not previous:
                connection.execute('INSERT INTO opportunities(id,title,organizer,mode,created_at) VALUES (?,?,?,?,?)',
                                   (op_id, claim.opportunity_title, claim.organizer, mode, now()))
                connection.execute('INSERT INTO packages(opportunity_id) VALUES (?)', (op_id,))
            connection.execute('UPDATE messages SET opportunity_id=? WHERE id=?', (op_id, claim.source_id))
            op = require_op(connection, op_id)
            if CLAIM_HANDLERS[claim.type](connection, claim, op_id, op, job_id):
                touched.add(op_id)
        for op_id in touched:
            touch(connection, op_id, 'requirements_updated', {'job_id': job_id}, reopen_closed=True)
        event(connection, 'import_applied', {'new_messages': len(fresh), **usage}, job_id=job_id)
        return {'new_messages': len(fresh), 'opportunities': sorted(touched), **usage}


def detail(store, op_id):
    with closing(store.connect()) as connection:
        op = require_op(connection, op_id)
        package = dict(connection.execute('SELECT * FROM packages WHERE opportunity_id=?', (op_id,)).fetchone())
        package['answers'] = json.loads(package.pop('answers_json'))
        requirements = [dict(r) for r in connection.execute('SELECT * FROM requirements WHERE opportunity_id=? ORDER BY id', (op_id,))]
        deadline = json.loads(op.pop('deadline_json')) if op['deadline_json'] else None
        blockers = []
        for req in requirements:
            answer = package['answers'].get(req['requirement_key'], {})
            if req['required'] and (not answer.get('answer', '').strip() or not answer.get('confirmed')):
                blockers.append(req['title'])
        if not requirements:
            blockers.append('No requirements have been reviewed yet')
        if not deadline or not deadline['selected']:
            blockers.append('Confirm the deadline or resolve its ambiguity')
        op.update(deadline=deadline, package=package, requirements=requirements, blockers=blockers,
                  messages=[dict(r) for r in connection.execute('SELECT * FROM messages WHERE opportunity_id=? ORDER BY received_at', (op_id,))],
                  receipts=[dict(r) for r in connection.execute('SELECT * FROM receipts WHERE opportunity_id=?', (op_id,))],
                  events=[dict(r) for r in connection.execute('SELECT * FROM events WHERE opportunity_id=? ORDER BY id DESC', (op_id,))],
                  conversation=[dict(r) for r in connection.execute('SELECT * FROM conversations WHERE opportunity_id=? ORDER BY id', (op_id,))])
        return op


def save_answer(store, op_id, key, answer, expected_revision, *, confirmed=True, fact_keys=None):
    with store.transaction() as connection:
        op = require_op(connection, op_id, expected_revision)
        req = connection.execute('SELECT * FROM requirements WHERE opportunity_id=? AND requirement_key=?', (op_id, key)).fetchone()
        if not req:
            raise ValueError('Unknown requirement')
        answer = answer.strip()
        if key.endswith('_url') and answer:
            url = urlparse(answer)
            if url.scheme not in {'http', 'https'} or not url.netloc:
                raise ValueError('Enter a complete http or https URL')
        if op['workflow'] == 'closed':
            raise Conflict('This opportunity is closed; its reviewed package is preserved')
        package = connection.execute('SELECT answers_json FROM packages WHERE opportunity_id=?', (op_id,)).fetchone()
        answers = json.loads(package[0])
        answers[key] = {'answer': answer, 'confirmed': confirmed, 'fact_keys': fact_keys or [],
                        'provenance': 'user_reviewed' if confirmed else 'draft', 'updated_at': now()}
        connection.execute('UPDATE packages SET answers_json=? WHERE opportunity_id=?', (json.dumps(answers), op_id))
        touch(connection, op_id, 'answer_reviewed' if confirmed else 'answer_drafted', {'key': key})
    return detail(store, op_id)


def confirm_deadline(store, op_id, source_id, expected_revision, due_at=None):
    with store.transaction() as connection:
        op = require_op(connection, op_id, expected_revision)
        if op['workflow'] == 'closed':
            raise Conflict('This opportunity is closed; import changed requirements before reopening review')
        if not op['deadline_json']:
            raise ValueError('No sourced deadline is available')
        deadline = json.loads(op['deadline_json'])
        candidates = [c for c in deadline['candidates'] if c['source_id'] == source_id]
        if not candidates:
            raise ValueError('Unknown deadline source')
        selected = dict(candidates[-1])
        value = due_at or selected['due_at']
        if not value:
            raise ValueError('Resolve the deadline with a timezone-aware timestamp')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError('Deadline must include a UTC offset')
        selected.update(due_at=parsed.astimezone(timezone.utc).isoformat(), confirmed=True,
                        resolved_by='user', ambiguity=None)
        deadline['selected'] = selected
        connection.execute('UPDATE opportunities SET deadline_json=? WHERE id=?', (json.dumps(deadline), op_id))
        touch(connection, op_id, 'deadline_confirmed', selected)
    return detail(store, op_id)


def approve(store, op_id, expected_revision):
    # BEGIN IMMEDIATE spans both the readiness read and the approval write.
    with store.transaction() as connection:
        op = require_op(connection, op_id, expected_revision)
        package = connection.execute('SELECT * FROM packages WHERE opportunity_id=?', (op_id,)).fetchone()
        answers = json.loads(package['answers_json'])
        required = list(connection.execute('SELECT requirement_key FROM requirements WHERE opportunity_id=? AND required=1', (op_id,)))
        deadline = json.loads(op['deadline_json']) if op['deadline_json'] else {}
        if not required or not deadline.get('selected') or any(not answers.get(r[0], {}).get('confirmed') or not answers.get(r[0], {}).get('answer', '').strip() for r in required):
            raise Conflict('Review every required answer and confirm the deadline before approval')
        if op['workflow'] in ('closed', 'cancelled'):
            raise Conflict('A closed or cancelled opportunity cannot be approved')
        connection.execute('UPDATE packages SET approval_revision=?,approval_hash=? WHERE opportunity_id=?',
                           (op['revision'], digest(answers), op_id))
        connection.execute("UPDATE opportunities SET workflow='ready' WHERE id=?", (op_id,))
        event(connection, 'package_approved', {'revision': op['revision'], 'content_hash': digest(answers)}, op_id)
    return detail(store, op_id)


def review_receipt(store, op_id, receipt_id, decision, expected_revision):
    with store.transaction() as connection:
        op = require_op(connection, op_id, expected_revision)
        receipt = connection.execute('SELECT * FROM receipts WHERE id=? AND opportunity_id=?', (receipt_id, op_id)).fetchone()
        if not receipt:
            raise ValueError('Unknown receipt')
        if receipt['reviewed']:
            raise Conflict('This receipt already has a recorded review decision')
        if decision == 'confirm' and receipt['verdict'] != 'review_required':
            raise Conflict('This receipt does not match. It cannot verify completion.')
        connection.execute('UPDATE receipts SET reviewed=1,verdict=? WHERE id=?',
                           ('confirmed' if decision == 'confirm' else 'rejected', receipt_id))
        if decision == 'confirm':
            connection.execute("UPDATE opportunities SET workflow='closed',completion_basis='receipt_confirmed' WHERE id=?", (op_id,))
        event(connection, 'receipt_' + decision, {'receipt_id': receipt_id, 'source_id': receipt['source_id'], 'revision': op['revision']}, op_id)
    return detail(store, op_id)


def mark_submitted(store, op_id, expected_revision):
    with store.transaction() as connection:
        op = require_op(connection, op_id, expected_revision)
        pkg = connection.execute('SELECT approval_revision FROM packages WHERE opportunity_id=?', (op_id,)).fetchone()
        if pkg[0] != op['revision'] or op['workflow'] != 'ready':
            raise Conflict('Approve the current package first')
        connection.execute("UPDATE opportunities SET workflow='awaiting_receipt',completion_basis='user_asserted' WHERE id=?", (op_id,))
        event(connection, 'submission_marked_by_user', {'revision': op['revision'], 'receipt_verified': False}, op_id)
    return detail(store, op_id)
