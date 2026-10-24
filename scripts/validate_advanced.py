"""Explicit live smoke check using only the bundled fictional opportunity and image."""
import argparse
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import yaml
from fastapi.testclient import TestClient

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from backend.app import create_app


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=BASE/'submission/advanced-live-evaluation.json')
    args=parser.parse_args()
    for k,v in json.loads(args.credentials.read_text()).items():
        if k in {'NEBIUS_API_KEY','NEBIUS_TOKEN_FACTORY_API_KEY'}:os.environ[k]=v
    config=yaml.safe_load((BASE/'config.yaml').read_text())
    records=[]
    with tempfile.TemporaryDirectory(prefix='followthrough-advanced-') as directory:
        with TestClient(create_app(Path(directory),config),base_url='http://127.0.0.1:8787') as client:
            client.get('/')
            d=client.post('/api/proposals/demo').json();pid=d['id']
            def call(path,body):
                nonlocal d
                start=time.monotonic()
                r=client.post(f'/api/proposals/{pid}'+path,json=body)
                if r.status_code!=200:raise RuntimeError(f'{path}: {r.status_code} {r.text[:400]}')
                d=r.json()
                return round((time.monotonic()-start)*1000)
            key='technical_approach'
            key=next(r['key'] for r in d['requirements'] if 'technical' in r['title'].lower())
            latency=call('/semantic-search',{'expected_revision':d['revision'],'requirement_key':key})
            result=d['retrieval'][key]
            assert result['current'] and result['candidates'] and not d['answers']
            assert any(c['relevant'] for c in result['candidates'])
            records.append({'case':'semantic_evidence','status':'passed','latency_ms':latency,'embedding':result['embedding'],
                'reranking':result['reranking'],'passages_searched':result['passages_searched'],'relevant_count':sum(c['relevant'] for c in result['candidates'])})
            source=base64.b64encode((BASE/'samples/scanned-amendment.png').read_bytes()).decode()
            latency=call(f'/sources?revision={d["revision"]}',{'filename':'scanned-amendment.png','base64':source,'vision':True,'amendment':True})
            s=d['sources'][-1];sid=s['id']
            assert not s['transcription_reviewed'] and '6 weeks' in s['text'] and '4 weeks' in s['text']
            blocked=client.post(f'/api/proposals/{pid}/sources/{sid}/analyze',json={'expected_revision':d['revision']})
            assert blocked.status_code==400
            records.append({'case':'vision_transcription','status':'passed','latency_ms':latency,'ingestion':s['ingestion'],'text':s['text']})
            call(f'/sources/{sid}/transcription',{'expected_revision':d['revision'],'text':s['text']})
            latency=call('/risk-review',{'expected_revision':d['revision']})
            review=d['risk_review']
            assert review['current'] and review['issues']
            assert any(i['severity']=='critical' and '6 weeks' in ' '.join(c['quote'] for c in i['citations']) and '4 weeks' in ' '.join(c['quote'] for c in i['citations']) and i['question'] for i in review['issues']),review
            records.append({'case':'cited_conflict_review','status':'passed','latency_ms':latency,'analysis':review['analysis'],
                            'summary':review['summary'],'issues':review['issues']})
    args.output.write_text(json.dumps({'scope':'Three fictional live smoke cases; not a quality benchmark or customer outcome measurement.',
        'evaluation_notes':'A repeat correctly identified conflicting dates under kind=amendment. The expectation checks cited conflicting durations and a clarification question rather than a category label. Browser QA exposed long-ID copying errors; short P1-style model references replaced them while original IDs remain code-controlled.',
        'reranking':'NVIDIA chat relevance assessment; the documented Qwen rerank model returned 404 on this account.', 'results':records},indent=2)+'\n')
    print(json.dumps([{'case':r['case'],'status':r['status'],'latency_ms':r['latency_ms']} for r in records]))

if __name__=='__main__':main()
