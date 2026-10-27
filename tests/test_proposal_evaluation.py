"""Evaluation cannot hide missed obligations behind valid quotes or duplicate predictions."""
import importlib
from pathlib import Path


def test_valid_quotation_does_not_erase_wrong_classification_or_duplicate_predictions(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    schema = importlib.import_module('backend.proposal_schema')
    evaluate = importlib.import_module('backend.proposal_evaluation')
    quote = 'An optional workbook may be attached as a separate file.'
    case = {'text':quote,'requirements':[{'quote':quote,'required':False,'attachment':True}], 'deadline':'absent'}
    raw = {'requirements':[{'key':'workbook','title':'Workbook','quote':quote,'required':True,'attachment':True}], 'deadline':None}
    result = evaluate.score(case,schema.ProposalAnalysis.model_validate(raw))
    assert result['valid_quotes'] == 1 and result['correct'] == 0 and result['missed'] and not result['passed']
    raw['requirements'][0]['required'] = False
    raw['requirements'] *= 2
    result = evaluate.score(case,schema.ProposalAnalysis.model_validate(raw))
    assert result['correct'] == 1 and result['predicted'] == 2 and not result['passed']
    summary = evaluate.summarize([dict(result,case='duplicate')])
    assert summary['labelled_requirement_precision'] == .5 and summary['labelled_requirement_recall'] == 1


def test_amendment_key_quantity_and_invented_deadline_are_scored_separately(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    schema = importlib.import_module('backend.proposal_schema')
    evaluate = importlib.import_module('backend.proposal_evaluation')
    quote = 'Provide two case studies.'
    case = {'text':quote+' Due next Friday.', 'requirements':[{'quote':quote,'required':True,'attachment':False,'key':'studies','title_terms':['two']}], 'deadline':None}
    raw = {'requirements':[{'key':'studies','title':'Two case studies','quote':quote,'required':True,'attachment':False}], 'deadline':None}
    assert evaluate.score(case,schema.ProposalAnalysis.model_validate(raw))['passed']
    raw['requirements'][0]['key'] = 'new_studies'
    assert not evaluate.score(case,schema.ProposalAnalysis.model_validate(raw))['passed']
    raw['requirements'][0]['key'] = 'studies'
    raw['requirements'][0]['title'] = 'Case studies'
    assert not evaluate.score(case,schema.ProposalAnalysis.model_validate(raw))['passed']
    raw['requirements'][0]['title'] = 'Two case studies'
    raw['deadline'] = {'quote':'Due next Friday.','due_at':'2026-10-30T17:00:00Z'}
    result = evaluate.score(case,schema.ProposalAnalysis.model_validate(raw))
    assert result['correct'] == 1 and not result['deadline_correct'] and not result['passed']
