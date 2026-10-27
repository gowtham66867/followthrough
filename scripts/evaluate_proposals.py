"""Run bounded, paid synthetic extraction checks; never silently use fixtures."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import sys
import time
import yaml

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from backend.models import Nebius
from backend.proposal_schema import ProposalAnalysis
from backend.proposal_evaluation import score, summarize
from backend.proposal_dates import supported_candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True, help='Explicitly consume Nebius credits')
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, choices=range(1,21), default=16)
    args = parser.parse_args()
    for name, value in json.loads(args.credentials.read_text()).items():
        if name in {'NEBIUS_API_KEY','NEBIUS_TOKEN_FACTORY_API_KEY'}:
            os.environ[name] = value
    config = yaml.safe_load((BASE/'config.yaml').read_text())
    cases = json.loads((BASE/'samples/evaluation-cases.json').read_text())['cases'][:args.limit]
    rows = []
    provider = Nebius(config)
    for case in cases:
        start = time.monotonic()
        try:
            raw, usage = provider.complete('proposal_extract.txt', {'source':{'id':case['id'],'text':case['text']},
                'existing_requirements':case.get('existing',[])}, thinking=False, max_tokens=1800)
            result = score(case, ProposalAnalysis.model_validate(raw))
            result.update({'usage':usage, 'output':raw})
            guarded = ProposalAnalysis.model_validate(raw)
            if guarded.deadline:
                guarded.deadline.due_at = supported_candidate(guarded.deadline.quote, guarded.deadline.due_at)
            result['application_guard_score'] = score(case, guarded)
        except Exception as exc:
            result = {'passed':False, 'expected':len(case['requirements']), 'predicted':0,
                      'correct':0, 'valid_quotes':0, 'deadline_correct':False,
                      'missed':[gold['quote'] for gold in case['requirements']],
                      'failures':[type(exc).__name__+': '+str(exc)[:400]]}
        result.update({'case':case['id'], 'category':case['category'], 'elapsed_ms':round((time.monotonic()-start)*1000)})
        rows.append(result)
        print(json.dumps({k:result[k] for k in ('case','passed','correct','expected','elapsed_ms')}), flush=True)
    totals = summarize(rows)
    totals['median_elapsed_ms'] = statistics.median(row['elapsed_ms'] for row in rows)
    totals['max_elapsed_ms'] = max(row['elapsed_ms'] for row in rows)
    totals['reported_prompt_tokens'] = sum(row.get('usage',{}).get('usage',{}).get('prompt_tokens',0) for row in rows)
    totals['reported_completion_tokens'] = sum(row.get('usage',{}).get('usage',{}).get('completion_tokens',0) for row in rows)
    report = {'created_at':datetime.now(timezone.utc).isoformat(), 'model':config['model'],
        'scope':'Author-labelled synthetic development set. Not customer data, an independent benchmark, a held-out evaluation or production accuracy.',
        'method':'One-to-one matching of exact labelled source phrases, required/optional and attachment flags, selected quantity terms in titles, amendment keys and sourced deadlines. Legitimate alternate decompositions may be penalized. Quote validity is textual grounding, not semantic correctness. One run per case; no statistical confidence claim.',
        'cost':'Token usage reported below; actual currency cost not measured. Failed attempts and retries may also consume credits. No customer time-saving or ROI measurements.',
        'guarded_summary':summarize([dict(row.get('application_guard_score',row),case=row['case']) for row in rows]),
        'summary':totals, 'results':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(totals))


if __name__ == '__main__':
    main()
