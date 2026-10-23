"""Proposal readiness contracts across real API, document parsing and SQLite persistence."""
import base64
import importlib
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile
import pytest
from fastapi.testclient import TestClient


def test_proposal_changes_cannot_reuse_approval_or_unrelated_evidence(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    app = importlib.import_module('backend.app').create_app
    with TestClient(app(tmp_path),base_url='http://127.0.0.1:8787') as client:
        client.get('/')
        d=client.post('/api/proposals/demo').json(); pid=d['id']
        def post(path,**body):
            nonlocal d
            response=client.post('/api/proposals/'+pid+path,json={'expected_revision':d['revision'],**body})
            assert response.status_code==200,response.text
            d=response.json(); return d
        for r in list(d['requirements']):post('/requirements/'+r['key']+'/review',decision='confirmed')
        post('/draft')
        for key,answer in list(d['answers'].items()):post('/answers/'+key,**{k:answer[k] for k in ('text','evidence_ids','exception')},reviewed=True)
        post('/deadline',source_id=d['deadline']['source_id'],due_at=d['deadline']['due_at'])
        assert not d['blockers']
        post('/approve'); approved=d['revision'];old_hash=d['approval']['hash']
        exported=client.get('/api/proposals/'+pid+'/export');assert exported.status_code==200
        with ZipFile(BytesIO(exported.content)) as package:
            with ZipFile(BytesIO(package.read('proposal.docx'))) as document:
                assert b'Northstar Customer Portal' in document.read('word/document.xml')
            report=json.loads(package.read('internal-review.json'));assert report['approval']['hash']==old_hash
        post('/demo-amendment')
        assert not d['approved_current'] and d['approval_history'][-1]['hash']==old_hash
        assert not d['answers']['delivery_plan']['reviewed']
        assert any('attachment' in x.lower() for x in d['blockers'])
        assert client.post('/api/proposals/'+pid+'/approve',json={'expected_revision':approved}).status_code==409
        assert client.get('/api/proposals/'+pid+'/export').status_code==409
        for r in list(d['requirements']):
            if r['status']=='proposed':post('/requirements/'+r['key']+'/review',decision='confirmed')
        # An unsupported certification remains blocked even if its author clicks reviewed.
        post('/answers/certification',text='We are ISO 27001 certified.',evidence_ids=[],reviewed=True,exception='')
        assert any('Unsupported answer' in x for x in d['blockers'])
        assert client.post('/api/proposals/'+pid+'/approve',json={'expected_revision':d['revision']}).status_code==409
        foreign=client.post('/api/proposals/demo').json()['evidence'][0]['id']
        assert client.post('/api/proposals/'+pid+'/answers/certification',json={'expected_revision':d['revision'],'text':'invented','evidence_ids':[foreign],'reviewed':True,'exception':''}).status_code==400
        # Preserve binary DOCX through real upload parser and exported attachments.
        files=importlib.import_module('backend.proposal_files')
        blob=files.proposal_docx({'title':'Security workbook','client':'Northstar','requirements':[],'answers':{}})
        response=client.post(f'/api/proposals/{pid}/sources?revision={d["revision"]}',json={'filename':'security.docx','base64':base64.b64encode(blob).decode(),'attachment':'security_workbook'})
        assert response.status_code==200,response.text
        d=response.json(); assert not any('Missing attachment' in x for x in d['blockers'])
        for key in ['delivery_plan','security_workbook','certification']:
            texts={'delivery_plan':'Four week discovery followed by agreed implementation milestones.','security_workbook':'Completed workbook attached for client review.','certification':'We do not hold ISO 27001 certification.'}
            post('/evidence',title=key,text=texts[key],approved=True,expires_on=None,id=None)
            evidence=d['evidence'][-1]
            post('/answers/'+key,text=evidence['text'],evidence_ids=[evidence['id']],reviewed=True,exception='')
        post('/deadline',source_id=d['deadline']['source_id'],due_at=d['deadline']['due_at'])
        post('/approve'); post('/submission');current_hash=d['approval']['hash']
        for text,kind,valid in [('Unrelated Event received your submission.','submission',False),('Northstar Customer Portal received your submission.','submission',True),('Northstar Customer Portal acknowledged your submission.','acknowledgement',True)]:
            response=client.post(f'/api/proposals/{pid}/sources?revision={d["revision"]}',json={'filename':'receipt.txt','text':text,'receipt':True})
            assert response.status_code==200;d=response.json();sid=d['sources'][-1]['id']
            response=client.post('/api/proposals/'+pid+'/receipts',json={'expected_revision':d['revision'],'source_id':sid,'quote':text,'kind':kind})
            assert response.status_code==(200 if valid else 400),response.text
            if valid:d=response.json()
        assert d['approved_current'] and d['approval']['hash']==current_hash and d['acknowledgement']
        with ZipFile(BytesIO(client.get('/api/proposals/'+pid+'/export').content)) as package:
            names=[n for n in package.namelist() if n.startswith('attachments/')]
            assert package.read(names[0])==blob
    with TestClient(app(tmp_path),base_url='http://127.0.0.1:8787') as client:
        client.get('/');d=client.get('/api/proposals/'+pid).json()
        assert d['acknowledgement'] and d['approved_current']


def test_quotes_are_anchored_by_code_and_ambiguous_or_invented_evidence_is_rejected(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    models=importlib.import_module('backend.models');schema=importlib.import_module('backend.schemas')
    message=schema.Message(id='source',thread_id='t',subject='RFP',sender='client@example.com',received_at='2026-10-23T00:00:00Z',body='Preface. Provide a technical approach. End.')
    raw={'claims':[{'type':'requirement','source_id':'source','quote':'Provide a technical approach.','span_start':0,'span_end':1,'opportunity_id':'client-rfp','opportunity_title':'Client RFP','organizer':'Client','key':'technical_approach','title':'Technical approach'}]}
    result=models.validate_evidence(schema.Extraction.model_validate(models.anchor_quotes(raw,[message])),[message])
    claim=result.claims[0];assert message.body[claim.span_start:claim.span_end]==claim.quote and claim.span_start>0
    for body,quote in [('Repeat. Repeat.','Repeat.'),('Real source','Invented quotation')]:
        message.body=body;raw['claims'][0]['quote']=quote
        with pytest.raises(ValueError):models.anchor_quotes(raw,[message])
    store=importlib.import_module('backend.store').Store(tmp_path)
    assert not store.query('SELECT * FROM proposals')
