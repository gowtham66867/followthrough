"""Bounded semantic shortlisting followed by NVIDIA relevance assessment."""
import math
from .domain import digest
from .models import Nebius
from .proposal_schema import EvidenceRanking
from .proposals import evidence_valid
from .store import Conflict, now


def fingerprint(d, key):
    requirement = next((r for r in d['requirements'] if r['key'] == key), None)
    return digest({'requirement': requirement, 'evidence': [e for e in d['evidence'] if evidence_valid(e)]})


def cosine(left, right):
    if len(left) != len(right):
        raise ValueError('Embedding dimensions changed during search')
    return sum(a*b for a,b in zip(left,right)) / (math.sqrt(sum(a*a for a in left))*math.sqrt(sum(b*b for b in right)))


def search(service, pid, revision, key):
    d = service.get(pid)
    if d['revision'] != revision:
        raise Conflict('Refresh before searching evidence')
    req = next((r for r in d['requirements'] if r['key'] == key and r['status'] != 'withdrawn'), None)
    if not req:
        raise ValueError('Choose an active requirement')
    chunks = []
    for e in d['evidence']:
        if evidence_valid(e):
            for start in range(0, len(e['text']), 1000):
                quote = e['text'][start:start+1000]
                chunks.append({'id': f'{e["id"]}:{start}', 'evidence_id': e['id'], 'version': e['version'],
                               'title': e['title'], 'quote': quote, 'start': start, 'end': start+len(quote)})
    if not chunks:
        raise ValueError('Add approved, unexpired company evidence first')
    if len(chunks) > 64:
        raise ValueError('Semantic search supports at most 64 evidence passages; shorten the evidence library')
    provider = Nebius(service.config)
    query = req['title']+'\n'+req['quote']
    vectors, embedding_usage = provider.embed([query] + [c['title']+'\n'+c['quote'] for c in chunks])
    for c,v in zip(chunks,vectors[1:]):
        c['similarity'] = round(cosine(vectors[0],v),6)
    shortlist = sorted(chunks,key=lambda c:-c['similarity'])[:8]
    by_id = {f'P{i+1}':c for i,c in enumerate(shortlist)}
    payload = [{'id':alias,'title':c['title'],'quote':c['quote']} for alias,c in by_id.items()]
    raw, ranking_usage = provider.complete('evidence_rank.txt', {'requirement': query, 'candidates': payload},
                                           model=service.config.get('reranking_model') or service.config.get('model'), thinking=False)
    ranking = EvidenceRanking.model_validate(raw)
    seen, candidates = set(), []
    for item in ranking.candidates:
        if item.id in seen or item.id not in by_id:
            raise ValueError('Reranking returned a duplicate or unknown evidence passage')
        seen.add(item.id)
        candidates.append({**by_id[item.id], 'relevant':item.relevant, 'reason':item.reason})
    if seen != set(by_id):
        raise ValueError('Reranking must assess each shortlisted passage')
    record = {'fingerprint':fingerprint(d,key), 'at':now(), 'method':'embedding_shortlist_nvidia_relevance_review',
              'candidates':candidates, 'passages_searched':len(chunks), 'embedding':embedding_usage, 'reranking':ranking_usage}
    def mutate(current):
        current.setdefault('retrieval',{})[key] = record
        return {'key':key,'method':record['method'],'passages_searched':len(chunks),'embedding':embedding_usage,'reranking':ranking_usage}
    return service.change(pid,revision,'semantic_evidence_searched',mutate,material=False)
