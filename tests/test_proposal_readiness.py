"""The impact projection, final review and submission gates agree on real persisted packages."""
from datetime import date,timedelta
import importlib
from pathlib import Path
from io import BytesIO
import json
from zipfile import ZipFile
from fastapi.testclient import TestClient


def test_amendment_impact_links_sources_evidence_owners_and_reopened_approval(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    factory=importlib.import_module('backend.app').create_app
    with TestClient(factory(tmp_path),base_url='http://127.0.0.1:8787') as client:
        client.get('/');d=client.post('/api/proposals/demo').json();pid=d['id']
        def post(path,**body):
            nonlocal d
            response=client.post('/api/proposals/'+pid+path,json={'expected_revision':d['revision'],**body})
            assert response.status_code==200,response.text
            d=response.json();return d
        def consistent():
            blocking=[i for i in d['readiness']['issues'] if i['blocking']]
            assert d['blockers']==[i['title'] for i in blocking]
            assert len(blocking)==d['readiness']['blocking_count']
            assert d['readiness']['ready_for_approval']==(not blocking)
            assert len({i['id'] for i in d['readiness']['issues']})==len(d['readiness']['issues'])
            assert all(i['action'] and i['target']['view'] for i in d['readiness']['issues'])
        consistent()
        assert any(not i['blocking'] and i['category']=='owners' and i['target']['section']=='owner' for i in d['readiness']['issues'])
        for r in list(d['requirements']):post('/requirements/'+r['key']+'/review',decision='confirmed')
        post('/draft')
        for key,a in list(d['answers'].items()):post('/answers/'+key,text=a['text'],evidence_ids=a['evidence_ids'],reviewed=True,exception='')
        post('/deadline',source_id=d['deadline']['source_id'],due_at=d['deadline']['due_at'])
        assert d['readiness']['status']=='ready_for_review'
        post('/approve');revision=d['revision'];approved=d['approval'].copy()
        assert d['readiness']['status']=='approved' and d['approved_current']
        d=client.get('/api/proposals/'+pid).json()
        assert d['revision']==revision and d['approval']==approved
        source=d['sources'][0]
        # An unanalyzed amendment must not present an apparently complete impact map.
        response=client.post(f'/api/proposals/{pid}/sources?revision={revision}',json={'filename':'Extra amendment.txt','text':'Client requires additional review.','amendment':True})
        assert response.status_code==200;d=response.json()
        pending=d['sources'][-1]
        assert d['impact']['pending_amendments']==[{'id':pending['id'],'filename':pending['filename']}]
        assert not d['approved_current'] and client.get('/api/proposals/'+pid+'/export').status_code==409
        service=importlib.import_module('backend.proposals').Proposals(client.app.state.store,{})
        analysis=importlib.import_module('backend.proposal_schema').ProposalAnalysis(requirements=[])
        d=service.apply_analysis(pid,d['revision'],pending['id'],analysis,{'model':'explicit test fixture'})
        post('/demo-amendment');consistent()
        rows={r['key']:r for r in d['impact']['rows']}
        delivery=rows['delivery_plan']
        assert delivery['change']=='changed' and delivery['previous']['source_id']==source['id']
        assert delivery['previous']['quote']!=delivery['source']['quote']
        assert not delivery['answer']['reviewed'] and delivery['answer']['present']
        assert delivery['evidence'] and delivery['evidence'][0]['id']==d['answers']['delivery_plan']['evidence_ids'][0]
        assert delivery['package_approval']['previous_revision']==approved['revision']
        assert d['readiness']['last_approval']['hash']==approved['hash']
        security=rows['security_workbook']
        assert security['change']=='added_by_amendment' and security['attachment_required'] and not security['attachments']
        issue=next(i for i in d['readiness']['issues'] if i['id']=='attachment:security_workbook')
        assert issue['target']=={'view':'Import','requirement_key':'security_workbook','source_id':None}
        post('/tasks',requirement_key='security_workbook',owner='Fictional security lead',due_on=None,done=True)
        security=next(r for r in d['impact']['rows'] if r['key']=='security_workbook')
        assert security['task']['done'] and security['task']['owner']=='Fictional security lead'
        assert 'attachment:security_workbook' in security['blocking_issue_ids']
        assert client.post('/api/proposals/'+pid+'/approve',json={'expected_revision':d['revision']}).status_code==409
        # No projection is persisted as mutable source of truth or included in the approval hash.
        raw=json.loads(client.app.state.store.query('SELECT document_json FROM proposals WHERE id=?',(pid,))[0]['document_json'])
        assert 'readiness' not in raw and 'impact' not in raw
    with TestClient(factory(tmp_path),base_url='http://127.0.0.1:8787') as client:
        client.get('/');d=client.get('/api/proposals/'+pid).json()
        assert d['readiness']['blocking_count']==len(d['blockers']) and not d['approved_current']
        assert next(r for r in d['impact']['rows'] if r['key']=='delivery_plan')['previous']['quote']==delivery['previous']['quote']


def test_expired_evidence_blocks_review_export_and_submission_even_when_content_hash_is_unchanged(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    factory=importlib.import_module('backend.app').create_app
    proposals=importlib.import_module('backend.proposals')
    tomorrow=date.today()+timedelta(days=1)
    with TestClient(factory(tmp_path),base_url='http://127.0.0.1:8787') as client:
        client.get('/');d=client.post('/api/proposals/demo').json();pid=d['id']
        def post(path,**body):
            nonlocal d
            r=client.post('/api/proposals/'+pid+path,json={'expected_revision':d['revision'],**body})
            assert r.status_code==200,r.text
            d=r.json()
        e=d['evidence'][0]
        post('/evidence',id=e['id'],title=e['title'],text=e['text'],approved=True,expires_on=tomorrow.isoformat())
        for r in list(d['requirements']):post('/requirements/'+r['key']+'/review',decision='confirmed')
        post('/draft')
        for key,a in list(d['answers'].items()):post('/answers/'+key,text=a['text'],evidence_ids=a['evidence_ids'],reviewed=True,exception='')
        post('/deadline',source_id=d['deadline']['source_id'],due_at=d['deadline']['due_at']);post('/approve')
        approval=d['approval'].copy()
        exported=client.get('/api/proposals/'+pid+'/export');assert exported.status_code==200
        with ZipFile(BytesIO(exported.content)) as archive:
            report=json.loads(archive.read('internal-review.json'))
            assert report['readiness']['status']=='approved' and report['impact']['rows']
        class Later(date):
            @classmethod
            def today(cls):return tomorrow+timedelta(days=1)
        monkeypatch.setattr(proposals,'date',Later)
        d=client.get('/api/proposals/'+pid).json()
        assert d['approval']==approval and not d['approved_current']
        assert d['readiness']['status']=='blocked' and not d['readiness']['ready_for_approval']
        issue=next(i for i in d['readiness']['issues'] if i['id']=='support:technical_approach')
        assert issue['blocking'] and issue['target']['requirement_key']=='technical_approach'
        row=next(r for r in d['impact']['rows'] if r['key']=='technical_approach')
        assert not row['evidence'][0]['valid'] and not row['answer']['supported']
        assert client.get('/api/proposals/'+pid+'/export').status_code==409
        assert client.post('/api/proposals/'+pid+'/submission',json={'expected_revision':d['revision']}).status_code==409
        assert client.post('/api/proposals/'+pid+'/approve',json={'expected_revision':d['revision']}).status_code==409
