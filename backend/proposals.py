"""Proposal state, evidence contracts and revision-specific review."""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import re
import uuid
from .domain import digest
from .models import Nebius
from .proposal_schema import ProposalAnalysis
from .store import Conflict, now


def locate(text, quote):
    start = text.find(quote)
    if not quote or start < 0:
        raise ValueError('Quotation does not occur verbatim in its source')
    if text.find(quote, start + 1) >= 0:
        raise ValueError('Quotation occurs more than once; select a longer unique passage')
    return {'start': start, 'end': start + len(quote)}


def package_content(d):
    payload = {k: d[k] for k in ('title', 'client', 'requirements', 'evidence', 'answers', 'deadline')}
    payload['sources'] = [s for s in d['sources'] if not s.get('receipt')]
    return payload


def evidence_valid(e):
    return e['approved'] and (not e.get('expires_on') or date.fromisoformat(e['expires_on']) >= date.today())


def answer_supported(d, answer):
    refs = [e for e in d['evidence'] if e['id'] in answer.get('evidence_ids', [])]
    return bool(answer.get('text', '').strip()) and bool(refs) and len(refs) == len(set(answer.get('evidence_ids', []))) and all(evidence_valid(e) for e in refs) and answer['text'] == '\n\n'.join(e['text'] for e in refs)


def blockers(d):
    from .proposal_readiness import issues
    return [item['title'] for item in issues(d) if item['blocking']]


class Proposals:
    def __init__(self, store, config):
        self.store, self.config = store, config

    def get(self, pid):
        rows = self.store.query('SELECT document_json FROM proposals WHERE id=?', (pid,))
        if not rows:
            raise LookupError('Proposal not found')
        d = json.loads(rows[0]['document_json'])
        from .proposal_retrieval import fingerprint as retrieval_fingerprint
        from .proposal_risks import fingerprint as risk_fingerprint
        for key, record in d.get('retrieval', {}).items():
            record['current'] = record['fingerprint'] == retrieval_fingerprint(d, key)
        if d.get('risk_review'):
            d['risk_review']['current'] = d['risk_review']['fingerprint'] == risk_fingerprint(d)
        from .proposal_readiness import issues, report, impact_map
        readiness_issues = issues(d)
        d['blockers'] = [i['title'] for i in readiness_issues if i['blocking']]
        d['approved_current'] = bool(d['approval'] and d['approval']['revision'] == d['revision'] and d['approval']['hash'] == digest(package_content(d)) and not d['blockers'])
        d['readiness'] = report(d, readiness_issues)
        d['impact'] = impact_map(d, readiness_issues)
        return d

    def list(self):
        return [self.get(row['id']) for row in self.store.query('SELECT id FROM proposals ORDER BY rowid DESC')]

    def create(self, title, client, *, fictional=False):
        d = {'id': uuid.uuid4().hex, 'title': title, 'client': client, 'revision': 1,
             'fictional': fictional, 'sources': [], 'requirements': [], 'evidence': [],
             'answers': {}, 'tasks': [], 'deadline': None, 'approval': None,
             'approval_history': [], 'history': [], 'submission': None, 'acknowledgement': None}
        with self.store.transaction() as c:
            c.execute('INSERT INTO proposals VALUES (?,?)', (d['id'], json.dumps(d)))
        return self.get(d['id'])

    def change(self, pid, revision, kind, mutate, *, material=True):
        with self.store.transaction() as c:
            row = c.execute('SELECT document_json FROM proposals WHERE id=?', (pid,)).fetchone()
            if not row:
                raise LookupError('Proposal not found')
            d = json.loads(row[0])
            if d['revision'] != revision:
                raise Conflict('Proposal changed. Refresh before saving this decision.')
            detail = mutate(d) or {}
            if material:
                if d['approval']:
                    d['approval_history'].append(d['approval'])
                d['approval'] = None
                d['revision'] += 1
                if d['submission']:
                    detail['previous_submission_preserved'] = True
            d['history'].append({'kind': kind, 'at': now(), 'revision': d['revision'], **detail})
            c.execute('UPDATE proposals SET document_json=? WHERE id=?', (json.dumps(d), pid))
        return self.get(pid)

    def add_source(self, pid, revision, filename, text, locations, *, amendment=False, receipt=False, attachment='', encoded='', ingestion=None):
        if receipt and (amendment or attachment):
            raise ValueError('Receipt sources cannot also be amendments or attachments')
        if not text.strip() or len(text) > 80000:
            raise ValueError('Source must contain 1 to 80000 readable characters')
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        def mutate(d):
            if attachment and attachment not in {r['key'] for r in d['requirements'] if r['attachment']}:
                raise ValueError('Choose a requirement that explicitly requests an attachment')
            if any(s['hash'] == content_hash and s.get('attachment', '') == attachment for s in d['sources']):
                raise Conflict('This source is already imported')
            sid = uuid.uuid4().hex
            d['sources'].append({'id': sid, 'filename': filename, 'text': text, 'hash': content_hash,
                                 'locations': locations, 'amendment': amendment, 'receipt': receipt,
                                 'attachment': attachment, 'original_base64': encoded, 'analyzed': False,
                                 'ingestion': ingestion, 'transcription_reviewed': False, 'at': now()})
            return {'source_id': sid, 'filename': filename}
        return self.change(pid, revision, 'source_imported', mutate, material=not receipt)

    def analyze(self, pid, revision, source_id):
        d = self.get(pid)
        if d['revision'] != revision:
            raise Conflict('Refresh before analyzing')
        source = next((s for s in d['sources'] if s['id'] == source_id), None)
        if not source or source.get('receipt') or source.get('attachment'):
            raise ValueError('Select an RFP or amendment source')
        if (source.get('ingestion') or {}).get('review_required') and not source.get('transcription_reviewed'):
            raise ValueError('Compare the visual transcription with the original pages and confirm it first')
        raw, usage = Nebius(self.config).complete('proposal_extract.txt', {
            'source': {'id': source_id, 'text': source['text']},
            'existing_requirements': [{'key': r['key'], 'title': r['title']} for r in d['requirements']],
        })
        analysis = ProposalAnalysis.model_validate(raw)
        return self.apply_analysis(pid, revision, source_id, analysis, usage)

    def apply_analysis(self, pid, revision, source_id, analysis, usage):
        def mutate(d):
            source = next((s for s in d['sources'] if s['id'] == source_id), None)
            if not source:
                raise ValueError('Unknown source')
            if (source.get('ingestion') or {}).get('review_required') and not source.get('transcription_reviewed'):
                raise ValueError('Review the visual transcription before applying requirements')
            seen, changes = set(), []
            for item in analysis.requirements:
                if item.key in seen:
                    raise ValueError('Duplicate requirement key')
                seen.add(item.key)
                span = locate(source['text'], item.quote)
                previous = next((r for r in d['requirements'] if r['key'] == item.key), None)
                if previous and previous['source_id'] == source_id and all(
                    previous[k] == getattr(item, k) for k in ('title', 'quote', 'required', 'attachment')
                ):
                    continue
                req = {**item.model_dump(), 'source_id': source_id, **span, 'status': 'proposed', 'version': (previous or {}).get('version', 0) + 1}
                if previous:
                    req['previous'] = {k: previous[k] for k in ('source_id', 'quote', 'title', 'version')}
                    d['requirements'][d['requirements'].index(previous)] = req
                    if item.key in d['answers']:
                        d['answers'][item.key]['reviewed'] = False
                    changes.append({'key': item.key, 'change': 'changed', 'previous_source_id': previous['source_id']})
                else:
                    d['requirements'].append(req)
                    changes.append({'key': item.key, 'change': 'added'})
            if analysis.deadline:
                span = locate(source['text'], analysis.deadline.quote)
                due = analysis.deadline.due_at
                if due and datetime.fromisoformat(due.replace('Z', '+00:00')).utcoffset() is None:
                    raise ValueError('Deadline needs an explicit timezone')
                from .proposal_dates import supported_candidate
                candidate = supported_candidate(analysis.deadline.quote, due)
                d['deadline'] = {**analysis.deadline.model_dump(), **span, 'due_at': candidate, 'source_id': source_id, 'confirmed': False}
            source['analyzed'] = True
            source['analysis'] = usage
            return {'source_id': source_id, 'changes': changes, 'model': usage.get('model'), 'usage': usage.get('usage'), 'latency_ms': usage.get('latency_ms')}
        return self.change(pid, revision, 'source_analyzed', mutate)

    def review_requirement(self, pid, revision, key, decision):
        def mutate(d):
            r = next((r for r in d['requirements'] if r['key'] == key), None)
            if not r:
                raise LookupError('Requirement not found')
            r['status'] = decision
            return {'key': key, 'decision': decision}
        return self.change(pid, revision, 'requirement_reviewed', mutate)

    def evidence(self, pid, body):
        if body.expires_on:
            date.fromisoformat(body.expires_on)
        def mutate(d):
            previous = next((e for e in d['evidence'] if e['id'] == body.id), None)
            if body.id and not previous:
                raise LookupError('Evidence not found')
            item = {'id': body.id or uuid.uuid4().hex, 'title': body.title, 'text': body.text,
                    'approved': body.approved, 'expires_on': body.expires_on, 'version': (previous or {}).get('version', 0) + 1}
            if previous:
                d['evidence'][d['evidence'].index(previous)] = item
            else:
                d['evidence'].append(item)
            return {'evidence_id': item['id'], 'version': item['version']}
        return self.change(pid, body.expected_revision, 'evidence_saved', mutate)

    def answer(self, pid, key, body):
        def mutate(d):
            if key not in {r['key'] for r in d['requirements']}:
                raise LookupError('Requirement not found')
            if not set(body.evidence_ids).issubset({e['id'] for e in d['evidence']}):
                raise ValueError('Evidence belongs to another opportunity or does not exist')
            d['answers'][key] = {'text': body.text, 'evidence_ids': body.evidence_ids,
                                 'reviewed': body.reviewed, 'exception': body.exception, 'at': now()}
            return {'key': key, 'supported': answer_supported(d, d['answers'][key]), 'exception_recorded': bool(body.exception)}
        return self.change(pid, body.expected_revision, 'answer_saved', mutate)

    def draft(self, pid, revision):
        def mutate(d):
            saved = []
            stop = {'the','and','for','with','provide','must','required','proposal','your','our','from','include','a','of','in','to','is','an','at','least'}
            for r in d['requirements']:
                if d['answers'].get(r['key'], {}).get('reviewed') or r['status'] == 'withdrawn':
                    continue
                terms = set(re.findall(r'[a-z]{3,}', r['title'].lower())) - stop
                candidates = []
                for e in d['evidence']:
                    score = len(terms & set(re.findall(r'[a-z]{3,}', (e['title'] + ' ' + e['text']).lower())))
                    if evidence_valid(e) and score:
                        candidates.append((score, e))
                selected = [e for _, e in sorted(candidates, key=lambda x: -x[0])[:2]]
                if selected:
                    d['answers'][r['key']] = {'text': '\n\n'.join(e['text'] for e in selected), 'evidence_ids': [e['id'] for e in selected], 'reviewed': False, 'exception': '', 'at': now()}
                    saved.append(r['key'])
            return {'drafted_keys': saved, 'method': 'Deterministic retrieval of approved evidence excerpts; relevance requires human review'}
        return self.change(pid, revision, 'evidence_excerpts_prepared', mutate)

    def deadline(self, pid, body):
        due = datetime.fromisoformat(body.due_at.replace('Z', '+00:00'))
        if due.utcoffset() is None:
            raise ValueError('Deadline requires a timezone')
        def mutate(d):
            if not d['deadline'] or d['deadline']['source_id'] != body.source_id:
                raise ValueError('Choose the extracted deadline source')
            d['deadline'].update(due_at=due.isoformat(), confirmed=True)
            return {'source_id': body.source_id}
        return self.change(pid, body.expected_revision, 'deadline_confirmed', mutate)

    def task(self, pid, body):
        if body.due_on:
            date.fromisoformat(body.due_on)
        def mutate(d):
            if body.requirement_key not in {r['key'] for r in d['requirements']}:
                raise ValueError('Unknown requirement')
            d['tasks'] = [t for t in d['tasks'] if t['requirement_key'] != body.requirement_key]
            d['tasks'].append(body.model_dump(exclude={'expected_revision'}))
            return {'requirement_key': body.requirement_key, 'done': body.done}
        return self.change(pid, body.expected_revision, 'task_saved', mutate, material=False)

    def approve(self, pid, revision):
        def mutate(d):
            issues = blockers(d)
            if issues:
                raise Conflict('Resolve readiness blockers before approval: ' + '; '.join(issues[:4]))
            d['approval'] = {'revision': d['revision'], 'hash': digest(package_content(d)), 'at': now(), 'approver': 'local workspace owner'}
            return {'hash': d['approval']['hash']}
        return self.change(pid, revision, 'package_approved', mutate, material=False)

    def report_submission(self, pid, revision):
        def mutate(d):
            if blockers(d) or not d['approval'] or d['approval']['revision'] != d['revision'] or d['approval']['hash'] != digest(package_content(d)):
                raise Conflict('Approve the current package first')
            d['submission'] = {'basis': 'user_reported', 'at': now(), 'revision': d['revision']}
        return self.change(pid, revision, 'submission_reported', mutate, material=False)

    def receipt(self, pid, body):
        def mutate(d):
            source = next((s for s in d['sources'] if s['id'] == body.source_id and s.get('receipt')), None)
            if not source:
                raise ValueError('Choose an imported receipt source')
            if (source.get('ingestion') or {}).get('review_required') and not source.get('transcription_reviewed'):
                raise ValueError('Review the visual transcription before confirming receipt evidence')
            locate(source['text'], body.quote)
            if d['title'].lower() not in body.quote.lower() or not re.search(r'\b(received|submitted|acknowledge|acknowledged)\b', body.quote, re.I):
                raise ValueError('Receipt must explicitly name this opportunity and confirm receipt or submission')
            record = {'basis': 'human_reviewed_source', 'source_id': body.source_id, 'quote': body.quote, 'at': now(), 'revision': d['revision']}
            if body.kind == 'submission':
                if not d['submission'] or d['submission']['revision'] != d['revision']:
                    raise Conflict('Report submission of this revision before confirming its evidence')
                d['submission'] = record
            else:
                if not d['submission'] or d['submission']['basis'] != 'human_reviewed_source':
                    raise Conflict('Confirm submission evidence before acknowledgement')
                d['acknowledgement'] = record
            return {'kind': body.kind, 'source_id': body.source_id}
        return self.change(pid, body.expected_revision, 'receipt_reviewed', mutate, material=False)
