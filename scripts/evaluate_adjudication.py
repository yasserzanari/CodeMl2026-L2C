"""Evaluate frozen automatic comparisons on explicitly adjudicated pairs only.

Never treats unreviewed candidates as negatives or human decisions as predictions.
Outputs describe the reviewed subset, not project-wide or official jury accuracy.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


FIELDS = {'diametre', 'quantite', 'espacement_mm', 'longueur_mm'}


def evaluate(run, labels, run_hash, split=None):
    records = {r['information']['id']: r['information'] for r in run['records']}
    predictions = {}
    for row in run['results']:
        if len(row['plan_ids']) == len(row['atelier_ids']) == 1:
            key = (row['plan_ids'][0], row['atelier_ids'][0])
            if key in predictions:
                raise ValueError('Duplicate automatic pair in source run')
            predictions[key] = row
    slices = defaultdict(Counter)
    excluded = Counter()
    cases = []
    seen = set()
    for label in labels:
        if label['project_id'] != run['project_id']:
            excluded['other_project'] += 1
            continue
        if split and label.get('split') != split:
            excluded['other_split'] += 1
            continue
        if label.get('source_run_sha256') != run_hash:
            raise ValueError('Label source hash differs from frozen run')
        key = (label.get('plan_record_id'), label.get('atelier_record_id'))
        if key in seen:
            raise ValueError('Duplicate adjudicated pair')
        seen.add(key)
        outcome = label['human_outcome']
        if outcome not in ('same_identity', 'different_identity'):
            excluded[outcome] += 1
            continue
        if not label.get('adjudicator'):
            raise ValueError('Resolved labels require an adjudicator')
        if key[0] not in records or key[1] not in records:
            raise ValueError('Unknown annotation in label')
        if records[key[0]]['source'] != 'plan' or records[key[1]]['source'] != 'atelier':
            raise ValueError('Wrong source roles in label')
        expected = set(label.get('confirmed_discrepancy_fields', []))
        if expected - FIELDS or (expected and outcome != 'same_identity'):
            raise ValueError('Invalid confirmed discrepancy fields')
        predicted = predictions.get(key)
        alert = bool(predicted and predicted['status'] == 'non_conforme')
        truth = outcome == 'same_identity' and bool(expected)
        # Abstention and a missed association count as missed detection for a known positive.
        category = ('tp' if truth else 'fp') if alert else ('fn' if truth else 'tn')
        predicted_fields = {d['field'] for d in (predicted or {}).get('differences', [])} if alert else set()
        family = records[key[0]]['type_element']
        for name in ('all', family):
            count = slices[name]
            count['reviewed_pairs'] += 1
            count[category] += 1
            count['unpaired_or_abstained'] += not predicted or predicted['status'] == 'a_verifier'
            count['false_identity_alerts'] += alert and outcome == 'different_identity'
            if outcome == 'same_identity':
                count['field_tp'] += len(expected & predicted_fields)
                count['field_fn'] += len(expected - predicted_fields)
                count['field_fp'] += len(predicted_fields - expected)
        cases.append({'plan_id':key[0], 'atelier_id':key[1], 'category':category,
                      'expected_fields':sorted(expected), 'predicted_fields':sorted(predicted_fields)})
    output = {}
    for name, count in slices.items():
        tp, fp, fn = count['tp'], count['fp'], count['fn']
        output[name] = dict(count) | {'precision_on_reviewed_subset':tp/(tp+fp) if tp+fp else None,
                                      'recall_on_reviewed_subset':tp/(tp+fn) if tp+fn else None}
    return {'project_id':run['project_id'], 'run_id':run['id'], 'source_run_sha256':run_hash,
            'split':split, 'slices':output, 'excluded':dict(excluded), 'cases':cases,
            'official_score':None, 'project_precision':None, 'project_recall':None,
            'limitation':'Conditional metrics on adjudicated pairs only. Unreviewed and unextracted elements are outside the denominator. No independent or exhaustive evaluation is claimed.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--labels', required=True, type=Path)
    parser.add_argument('--split', choices=['development','validation','test'])
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output = args.out.resolve()
    if output == repo or repo in output.parents:
        parser.error('Keep evaluation results outside the source repository.')
    if output.exists():
        parser.error('Choose a new output file; previous evidence must be preserved.')
    raw = args.run.read_bytes()
    labels = json.loads(args.labels.read_text('utf-8'))
    if labels.get('schema_version') != 'l2c-adjudicated-labels-v1':
        parser.error('Use validated-labels.json produced by prepare_adjudication.py validate.')
    try:
        report = evaluate(json.loads(raw), labels['labels'], hashlib.sha256(raw).hexdigest(), args.split)
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))
    report['labels_sha256'] = hashlib.sha256(args.labels.read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2), 'utf-8')
    print(json.dumps({'output':str(output),'reviewed_pairs':len(report['cases']),
                      'official_score':None}))


if __name__ == '__main__':
    main()
