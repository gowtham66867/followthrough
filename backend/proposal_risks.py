"""Source-grounded advisory review with explicit, auditable human dispositions."""
import uuid
from .domain import digest
from .models import Nebius
from .proposal_schema import RiskAnalysis
from .proposals import locate, evidence_valid
from .store import Conflict, now


def fingerprint(d):
    return digest({'sources':[{k:s[k] for k in ('id','hash')} for s in d['sources'] if not s.get('receipt') and not s.get('attachment')],
                   'requirements':d['requirements'], 'evidence':[e for e in d['evidence'] if evidence_valid(e)], 'deadline':d['deadline']})


def review(service, pid, revision):
    d = service.get(pid)
    if d['revision'] != revision:
        raise Conflict('Refresh before conflict review')
    sources = [s for s in d['sources'] if not s.get('receipt') and not s.get('attachment')]
    if not sources or not d['requirements']:
        raise ValueError('Import and analyze an RFP before conflict review')
    if any((s.get('ingestion') or {}).get('review_required') and not s.get('transcription_reviewed') for s in sources):
        raise ValueError('Review each visual transcription before conflict review')
    if sum(len(s['text']) for s in sources) + sum(len(e['text']) for e in d['evidence'] if evidence_valid(e)) > 100000:
        raise ValueError('Conflict review is limited to 100000 context characters; split this opportunity')
    model = service.config.get('reasoning_model')
    if not model:
        raise ValueError('Configure reasoning_model before requesting deeper review')
    raw, usage = Nebius(service.config).complete('proposal_risks.txt', {
        'sources':[{k:s[k] for k in ('id','filename','text','amendment')} for s in sources],
        'requirements':d['requirements'], 'evidence':[e for e in d['evidence'] if evidence_valid(e)],
        'deadline':d['deadline']}, model=model, thinking=True, max_tokens=10000)
    analysis = RiskAnalysis.model_validate(raw)
    by_id = {s['id']:s for s in sources}
    keys = {r['key'] for r in d['requirements']}
    issues = []
    for issue in analysis.issues:
        if not set(issue.requirement_keys).issubset(keys):
            raise ValueError('Conflict review referenced an unknown requirement')
        citations = []
        for ref in issue.citations:
            source = by_id.get(ref.source_id)
            if not source:
                raise ValueError('Conflict review referenced an unknown source')
            citations.append({**ref.model_dump(), **locate(source['text'],ref.quote)})
        issues.append({**issue.model_dump(), 'citations':citations,'id':uuid.uuid4().hex,'decision':None})
    record = {'fingerprint':fingerprint(d),'at':now(),'summary':analysis.summary,'issues':issues,'analysis':usage}
    def mutate(current):
        if current.get('risk_review'):
            current.setdefault('risk_review_history',[]).append(current['risk_review'])
        current['risk_review'] = record
        if current['approval']:
            current['approval_history'].append(current['approval']);current['approval'] = None
        return {'model':model,'issue_count':len(issues),'usage':usage}
    return service.change(pid,revision,'conflicts_reviewed_with_nvidia',mutate,material=False)


def decide(service, pid, issue_id, body):
    def mutate(d):
        review = d.get('risk_review')
        if not review or review['fingerprint'] != fingerprint(d):
            raise Conflict('Conflict review is outdated; run it again before deciding')
        issue = next((i for i in review['issues'] if i['id']==issue_id),None)
        if not issue:
            raise LookupError('Review finding not found')
        issue['decision'] = {'decision':body.decision,'rationale':body.rationale,'at':now(),'by':'local workspace owner'}
        if d['approval']:
            d['approval_history'].append(d['approval']);d['approval'] = None
        return {'issue_id':issue_id,'decision':body.decision,'rationale':body.rationale}
    return service.change(pid,body.expected_revision,'conflict_disposition_recorded',mutate,material=False)
