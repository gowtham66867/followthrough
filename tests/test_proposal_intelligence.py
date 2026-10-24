"""Live HTTP contracts for semantic advice, revision safety and reviewed visual sources."""
import base64
from contextlib import contextmanager
import importlib
from io import BytesIO
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler,HTTPServer
import pytest
from fastapi.testclient import TestClient
from PIL import Image


@contextmanager
def workspace(tmp_path,monkeypatch,responder):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    models=importlib.import_module('backend.models')
    captured=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            captured.append(body)
            result=responder(self.path,body)
            payload=json.dumps(result).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def log_message(self,*args):pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    monkeypatch.setattr(models,'ENDPOINT',f'http://127.0.0.1:{server.server_port}/v1')
    monkeypatch.setenv('NEBIUS_API_KEY','synthetic-local-test-key')
    config={'model':'nvidia/extract','embedding_model':'test/embedding','reranking_model':'nvidia/rank',
            'reasoning_model':'nvidia/reason','vision_model':'nvidia/vision','enable_thinking':False}
    try:
        with TestClient(importlib.import_module('backend.app').create_app(tmp_path,config),base_url='http://127.0.0.1:8787') as client:
            client.get('/');yield client,captured
    finally:
        server.shutdown();worker.join(timeout=5);server.server_close()


def chat(raw):
    return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(raw)}}],'usage':{'total_tokens':100}}


def test_semantic_and_reasoning_advice_cannot_bypass_evidence_quotes_or_revision_review(tmp_path,monkeypatch):
    mode={'invalid':False,'nan':False}
    def respond(path,body):
        if path.endswith('/embeddings'):
            if mode.get('concurrent_edit'):
                mode.pop('concurrent_edit')()
            return {'data':[{'index':i,'embedding':[float('nan') if mode['nan'] else 1,i/100+0.1]} for i,_ in enumerate(body['input'])]}
        payload=json.loads(body['messages'][1]['content'])
        if body['model']=='nvidia/rank':
            return chat({'candidates':[{'id':c['id'],'relevant':True,'reason':'Specific supporting facts need human review.'} for c in payload['candidates']]})
        source=payload['sources'][0]
        return chat({'summary':'Verify delivery obligations.','issues':[{'kind':'conflict','severity':'critical','summary':'Delivery window needs clarification.',
            'question':'Which delivery window applies?','requirement_keys':['delivery_plan'],
            'citations':[{'source_id':source['id'],'quote':'invented quote' if mode['invalid'] else 'Provide a delivery plan for a twelve week implementation.'}]}]})
    with workspace(tmp_path,monkeypatch,respond) as (client,captured):
        d=client.post('/api/proposals/demo').json();pid=d['id']
        def post(path,**body):
            nonlocal d
            r=client.post('/api/proposals/'+pid+path,json={'expected_revision':d['revision'],**body})
            assert r.status_code==200,r.text
            d=r.json();return d
        # Keep a human-reviewed answer intact even when semantic suggestions arrive.
        e=d['evidence'][0]
        post('/answers/technical_approach',text=e['text'],evidence_ids=[e['id']],reviewed=True)
        answer=d['answers']['technical_approach'].copy()
        post('/evidence',title='Unapproved secret',text='DO_NOT_SEND_UNAPPROVED',approved=False)
        post('/evidence',title='Expired',text='DO_NOT_SEND_EXPIRED',approved=True,expires_on='2000-01-01')
        old=d['revision'];post('/semantic-search',requirement_key='technical_approach')
        assert d['revision']==old and d['answers']['technical_approach']==answer
        assert d['retrieval']['technical_approach']['current']
        assert all('DO_NOT_SEND' not in str(c) for c in captured)
        mode['nan']=True
        failed=client.post('/api/proposals/'+pid+'/semantic-search',json={'expected_revision':old,'requirement_key':'technical_approach'})
        assert failed.status_code==400
        assert client.get('/api/proposals/'+pid).json()['retrieval']==d['retrieval']
        mode['nan']=False
        # Reject fabricated citations atomically; valid findings require explicit disposition.
        mode['invalid']=True
        assert client.post('/api/proposals/'+pid+'/risk-review',json={'expected_revision':old}).status_code==400
        assert not client.get('/api/proposals/'+pid).json().get('risk_review')
        mode['invalid']=False;post('/risk-review')
        finding=d['risk_review']['issues'][0]
        assert any('Decide review finding' in b for b in d['blockers'])
        source=next(s for s in d['sources'] if s['id']==finding['citations'][0]['source_id']);ref=finding['citations'][0]
        assert source['text'][ref['start']:ref['end']]==ref['quote']
        post('/risk-review/'+finding['id'],decision='accepted',rationale='Client clarification has been requested by the proposal owner.')
        assert not any('Decide review finding' in b for b in d['blockers'])
        e=d['evidence'][0]
        post('/evidence',id=e['id'],title=e['title'],text=e['text']+' Revised.',approved=True)
        assert not d['retrieval']['technical_approach']['current'] and not d['risk_review']['current']
        assert 'Refresh outdated conflict review' in d['blockers']
        assert client.post('/api/proposals/'+pid+'/risk-review/'+finding['id'],json={'expected_revision':d['revision'],'decision':'dismissed','rationale':'This is now outdated.'}).status_code==409
        assert client.get('/api/proposals/'+pid+'/export').status_code==409
        service=importlib.import_module('backend.proposals').Proposals(importlib.import_module('backend.store').Store(tmp_path),{})
        schema=importlib.import_module('backend.proposal_schema')
        mode['concurrent_edit']=lambda:service.evidence(pid,schema.EvidenceInput(expected_revision=d['revision'],title='Concurrent edit',text='A new verified fact.',approved=True))
        stale=client.post('/api/proposals/'+pid+'/semantic-search',json={'expected_revision':d['revision'],'requirement_key':'technical_approach'})
        assert stale.status_code==409
        assert client.get('/api/proposals/'+pid).json()['answers']['technical_approach']==answer
        assert any(c.get('model')=='nvidia/reason' and c['chat_template_kwargs']['enable_thinking'] for c in captured)
    # Persisted advice retains stale state across a real application restart.
    with workspace(tmp_path,monkeypatch,respond) as (client,_):
        d=client.get('/api/proposals/'+pid).json();assert not d['risk_review']['current']


def test_visual_import_requires_pixel_review_and_keeps_original_pages_and_quotes(tmp_path,monkeypatch):
    transcript='Provide a delivery plan.\n| Item | Due |\n| Workbook | With proposal |'
    def respond(path,body):
        if body['model']=='nvidia/vision':
            assert body['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
            return chat({'text':transcript,'uncertain_passages':['Check workbook due date.']})
        return chat({'requirements':[{'key':'delivery_plan','title':'Delivery plan','quote':'Provide a delivery plan.','required':True,'attachment':False}],'deadline':None})
    image=Image.new('RGB',(300,200),'white');buffer=BytesIO();image.save(buffer,format='PNG')
    encoded=base64.b64encode(buffer.getvalue()).decode()
    with workspace(tmp_path,monkeypatch,respond) as (client,captured):
        d=client.post('/api/proposals',json={'title':'Visual test','client':'Fictional Client'}).json();pid=d['id']
        def post(path,**body):
            nonlocal d
            r=client.post('/api/proposals/'+pid+path,json={'expected_revision':d['revision'],**body})
            assert r.status_code==200,r.text
            d=r.json();return d
        imported=client.post(f'/api/proposals/{pid}/sources?revision={d["revision"]}',json={'filename':'scan.png','base64':encoded,'vision':True})
        assert imported.status_code==200,imported.text
        d=imported.json();s=d['sources'][0];sid=s['id']
        assert any('Review visual transcription' in b for b in d['blockers'])
        page=client.get(f'/api/proposals/{pid}/sources/{sid}/pages/1')
        assert page.status_code==200 and Image.open(BytesIO(page.content)).size==(300,200)
        assert client.get(f'/api/proposals/{pid}/sources/{sid}/pages/2').status_code==400
        assert client.post(f'/api/proposals/{pid}/sources/{sid}/analyze',json={'expected_revision':d['revision']}).status_code==400
        original=s['text']
        corrected=original.replace('With proposal','Before kickoff')
        post('/sources/'+sid+'/transcription',text=corrected)
        assert d['sources'][0]['machine_transcription']==original and d['sources'][0]['text']==corrected
        post('/sources/'+sid+'/analyze')
        req=d['requirements'][0];assert corrected[req['start']:req['end']]==req['quote']
        assert d['sources'][0]['original_base64']==encoded
        assert client.post(f'/api/proposals/{pid}/sources/{sid}/transcription',json={'expected_revision':d['revision'],'text':transcript}).status_code==409
        # Multipage image-only PDFs preserve every page through rendering and transcription.
        # Pillow emits an image-only multipage PDF, exercising actual PDF render + model path.
        pdf=BytesIO();image.save(pdf,format='PDF',save_all=True,append_images=[image])
        r=client.post(f'/api/proposals/{pid}/sources?revision={d["revision"]}',json={'filename':'scan.pdf','base64':base64.b64encode(pdf.getvalue()).decode(),'vision':True})
        assert r.status_code==200,r.text
        pdf_source=r.json()['sources'][-1]
        assert len(pdf_source['ingestion']['pages'])==2
        assert client.get(f'/api/proposals/{pid}/sources/{pdf_source["id"]}/pages/2').status_code==200
        assert len([c for c in captured if c.get('model')=='nvidia/vision'])==3
