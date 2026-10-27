"""Transparent one-to-one scoring of synthetic, author-labelled extraction cases."""
from .proposals import locate
from datetime import datetime


def same_instant(left, right):
    try:
        a = datetime.fromisoformat(left.replace('Z', '+00:00'))
        b = datetime.fromisoformat(right.replace('Z', '+00:00'))
        return a.utcoffset() is not None and b.utcoffset() is not None and a == b
    except (ValueError, AttributeError):
        return False


def score(case, analysis):
    predictions = analysis.requirements
    matched = set()
    correct = 0
    citations = 0
    failures = []
    for prediction in predictions:
        try:
            locate(case['text'], prediction.quote)
            citations += 1
        except ValueError:
            failures.append('Invalid or ambiguous source quote: ' + prediction.title)
            continue
        found = next((i for i, gold in enumerate(case['requirements'])
                      if i not in matched and (gold['quote'].rstrip('.').lower() in prediction.quote.rstrip('.').lower()
                          or prediction.quote.rstrip('.').lower() in gold['quote'].rstrip('.').lower())
                      and gold['required'] == prediction.required
                      and gold['attachment'] == prediction.attachment
                      and all(term.lower() in prediction.title.lower() for term in gold.get('title_terms', []))
                      and (not gold.get('key') or gold['key'] == prediction.key)), None)
        if found is None:
            failures.append('Unmatched requirement or classification/key error: ' + prediction.title)
        else:
            matched.add(found)
            correct += 1
    missed = [gold['quote'] for i, gold in enumerate(case['requirements']) if i not in matched]
    deadline = analysis.deadline
    if case['deadline'] == 'absent':
        deadline_ok = deadline is None
    elif case['deadline'] is None:
        deadline_ok = deadline is None or deadline.due_at is None
    else:
        deadline_ok = bool(deadline and same_instant(deadline.due_at, case['deadline']))
    if deadline:
        try:
            locate(case['text'], deadline.quote)
        except ValueError:
            deadline_ok = False
    if not deadline_ok:
        failures.append('Deadline missing, invented, incorrectly resolved or not uniquely cited')
    return {'passed':not missed and not failures, 'expected':len(case['requirements']),
            'predicted':len(predictions), 'correct':correct, 'valid_quotes':citations,
            'deadline_correct':deadline_ok, 'missed':missed, 'failures':failures}


def summarize(rows):
    total = sum(row['expected'] for row in rows)
    predicted = sum(row['predicted'] for row in rows)
    correct = sum(row['correct'] for row in rows)
    return {'cases':len(rows), 'passed':sum(row['passed'] for row in rows),
            'labelled_requirements':total, 'predicted_requirements':predicted,
            'matched_requirements':correct,
            'labelled_requirement_recall':round(correct / total, 4) if total else None,
            'labelled_requirement_precision':round(correct / predicted, 4) if predicted else None,
            'quote_validity':round(sum(row['valid_quotes'] for row in rows)/predicted,4) if predicted else None,
            'deadline_cases_correct':sum(row['deadline_correct'] for row in rows),
            'case_failures':[row['case'] for row in rows if not row['passed']]}
