"""Concrete handlers for validated source claims."""
import json
from email.utils import parseaddr
from .store import event


def apply_registration(connection, claim, op_id, op, job_id):
    if claim.application_ref and claim.application_ref in claim.quote:
        connection.execute('UPDATE opportunities SET application_ref=COALESCE(application_ref,?) WHERE id=?', (claim.application_ref, op_id))
    event(connection, 'registration_found', {'source_id': claim.source_id, 'quote': claim.quote}, op_id, job_id)
    return False


def apply_requirement(connection, claim, op_id, op, job_id):
    old = connection.execute('SELECT * FROM requirements WHERE opportunity_id=? AND requirement_key=?', (op_id, claim.key)).fetchone()
    if old and old['title'] == claim.title and bool(old['required']) == claim.required:
        event(connection, 'requirement_reminder', {'key': claim.key, 'source_id': claim.source_id, 'quote': claim.quote}, op_id, job_id)
        return False
    connection.execute('''INSERT INTO requirements VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(opportunity_id,requirement_key) DO UPDATE SET title=excluded.title,
        required=excluded.required,source_id=excluded.source_id,quote=excluded.quote,
        span_start=excluded.span_start,span_end=excluded.span_end,revision=excluded.revision''',
        (op_id + ':' + claim.key, op_id, claim.key, claim.title, int(claim.required),
         claim.source_id, claim.quote, claim.span_start, claim.span_end, op['revision'] + 1))
    event(connection, 'requirement_added' if not old else 'requirement_changed',
          {'key': claim.key, 'title': claim.title, 'source_id': claim.source_id, 'quote': claim.quote,
           'previous': dict(old) if old else None}, op_id, job_id)
    return True


def apply_deadline(connection, claim, op_id, op, job_id):
    deadline = json.loads(op['deadline_json']) if op['deadline_json'] else {'candidates': [], 'selected': None}
    if any(c['due_at'] == claim.due_at and c['ambiguity'] == claim.ambiguity for c in deadline['candidates']):
        event(connection, 'deadline_reminder', {'source_id': claim.source_id, 'quote': claim.quote}, op_id, job_id)
        return False
    candidate = {'source_id': claim.source_id, 'quote': claim.quote, 'due_at': claim.due_at,
                 'timezone': claim.timezone, 'ambiguity': claim.ambiguity, 'confirmed': False}
    deadline['candidates'].append(candidate)
    deadline['selected'] = None
    connection.execute('UPDATE opportunities SET deadline_json=? WHERE id=?', (json.dumps(deadline), op_id))
    event(connection, 'deadline_proposed', candidate, op_id, job_id)
    return True


def apply_receipt(connection, claim, op_id, op, job_id):
    source = connection.execute('SELECT * FROM messages WHERE id=?', (claim.source_id,)).fetchone()
    known_senders = {parseaddr(r['sender'])[1].lower() for r in connection.execute(
        "SELECT sender FROM messages WHERE id IN (SELECT json_extract(detail_json,'$.source_id') FROM events WHERE opportunity_id=? AND kind='registration_found')", (op_id,))}
    ref_ok = bool(op['application_ref'] and claim.application_ref == op['application_ref'] and claim.application_ref in claim.quote)
    sender_ok = parseaddr(source['sender'])[1].lower() in known_senders
    title_ok = op['title'].casefold() in claim.quote.casefold()
    eligible = claim.receipt_type == 'submission' and ref_ok and sender_ok and title_ok
    reason = ('Event reference, title and a previously seen sender match. Review the source before confirming.' if eligible
              else 'Not a matching submission receipt: event reference, title, sender or receipt type does not match.')
    connection.execute('INSERT OR IGNORE INTO receipts VALUES (?,?,?,?,?,?,?,0)',
                       ('receipt-' + claim.source_id, op_id, claim.source_id, claim.quote,
                        claim.application_ref, 'review_required' if eligible else 'mismatch', reason))
    event(connection, 'receipt_candidate', {'source_id': claim.source_id, 'eligible': eligible, 'reason': reason}, op_id, job_id)
    return False


CLAIM_HANDLERS = {
    'registration': apply_registration,
    'requirement': apply_requirement,
    'deadline': apply_deadline,
    'receipt': apply_receipt,
}
