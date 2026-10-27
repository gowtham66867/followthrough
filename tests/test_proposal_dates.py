"""A model's precise timestamp must not erase missing source precision."""
import importlib
from pathlib import Path


def test_missing_time_or_zone_remains_unresolved_in_persisted_proposal(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    Proposals = importlib.import_module('backend.proposals').Proposals
    Store = importlib.import_module('backend.store').Store
    Analysis = importlib.import_module('backend.proposal_schema').ProposalAnalysis
    service = Proposals(Store(tmp_path), {})
    for quote in ('Submit October 29, 2026 at 17:00.', 'Submit October 29, 2026.'):
        d = service.create('Fictional precision test','Fictional Client')
        d = service.add_source(d['id'],d['revision'],'date.txt',quote,[{'location':'Text','start':0}])
        analysis = Analysis.model_validate({'requirements':[], 'deadline':{'quote':quote,'due_at':'2026-10-29T17:00:00Z'}})
        d = service.apply_analysis(d['id'],d['revision'],d['sources'][0]['id'],analysis,{'mode':'fixture'})
        persisted = service.get(d['id'])
        assert persisted['deadline']['due_at'] is None and not persisted['deadline']['confirmed']
        assert persisted['deadline']['quote'] == quote and persisted['blockers']


def test_explicit_timestamp_stays_a_human_confirmation_candidate(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    guard = importlib.import_module('backend.proposal_dates').supported_candidate
    candidate = '2026-10-29T17:00:00Z'
    assert guard('Submit October 29, 2026 at 17:00 UTC.',candidate) == candidate
    assert guard('Submit 2026-10-29T17:00:00Z.',candidate) == candidate
    assert guard('Submit next Friday.',candidate) is None
