"""Evaluate raw OCR confidence scores against a frozen, independently reviewed set.

Reference JSON schema (``l2c-confidence-reference-v1``)::

    {
      "schema_version": "l2c-confidence-reference-v1",
      "revision": "r1",
      "annotator": {"id": "eng-1", "qualified": true,
                    "qualification_reference": "qualification record"},
      "source_run_sha256": "<64 hex chars>",
      "split": {"name": "test", "independent": true,
                "independent_of": ["training", "calibration"],
                "project_ids": ["project-1"],
                "document_ids": ["doc-1"], "frozen_at": "2026-10-04"},
      "samples": [{"id": "page1-field1", "project_id": "project-1",
                   "document_id": "doc-1", "raw_ocr_score": 0.8,
                   "correct": true}],
      "frozen_payload_sha256": "<digest defined below>"
    }

The payload digest is SHA-256 of UTF-8 JSON for ``{"split": split,
"samples": samples}``, serialized with sorted keys, no insignificant spaces,
and ``ensure_ascii=False``. It freezes both the declared split and its labels.
This tool computes descriptive Brier/ECE statistics; it does not calibrate a
model or establish engineering approval or project-wide performance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 'l2c-confidence-reference-v1'
MIN_LABELS_FOR_DESCRIPTIVE_REVIEW = 30
MIN_PER_OUTCOME_FOR_DESCRIPTIVE_REVIEW = 5
_SHA256 = re.compile(r'^[0-9a-f]{64}$')


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_reference(reference: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate provenance and schema before allowing metric calculation."""
    if reference.get('schema_version') != SCHEMA_VERSION:
        raise ValueError(f'reference schema_version must be {SCHEMA_VERSION!r}')
    if not _nonempty_string(reference.get('revision')):
        raise ValueError('A frozen reference revision is required')
    annotator = reference.get('annotator')
    if (not isinstance(annotator, dict) or not _nonempty_string(annotator.get('id'))
            or annotator.get('qualified') is not True
            or not _nonempty_string(annotator.get('qualification_reference'))):
        raise ValueError('A qualified annotator and qualification_reference are required')
    source_hash = reference.get('source_run_sha256')
    if not isinstance(source_hash, str) or not _SHA256.fullmatch(source_hash):
        raise ValueError('A valid source_run_sha256 is required')

    split = reference.get('split')
    if not isinstance(split, dict):
        raise ValueError('A frozen independent split declaration is required')
    if split.get('name') not in ('test', 'independent_validation'):
        raise ValueError('Validation requires a test or independent_validation split')
    if split.get('independent') is not True:
        raise ValueError('The declared split must be independent')
    independent_of = split.get('independent_of')
    if not isinstance(independent_of, list) or not {'training', 'calibration'}.issubset(independent_of):
        raise ValueError('The split must be independent_of training and calibration data')
    if not _nonempty_string(split.get('frozen_at')):
        raise ValueError('A frozen_at timestamp or date is required')
    projects, documents = split.get('project_ids'), split.get('document_ids')
    if (not isinstance(projects, list) or not projects or
            not all(_nonempty_string(item) for item in projects) or len(set(projects)) != len(projects)):
        raise ValueError('split.project_ids must be a non-empty list of unique ids')
    if (not isinstance(documents, list) or not documents or
            not all(_nonempty_string(item) for item in documents) or len(set(documents)) != len(documents)):
        raise ValueError('split.document_ids must be a non-empty list of unique ids')

    samples = reference.get('samples')
    if not isinstance(samples, list) or not samples:
        raise ValueError('At least one labeled sample is required')
    ids: set[str] = set()
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError('Each sample must be an object')
        sample_id = sample.get('id')
        if not _nonempty_string(sample_id) or sample_id in ids:
            raise ValueError('Sample ids must be non-empty and unique')
        ids.add(sample_id)
        if sample.get('project_id') not in projects or sample.get('document_id') not in documents:
            raise ValueError('Every sample must belong to the frozen project/document split')
        score = sample.get('raw_ocr_score')
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('raw_ocr_score must be a finite raw score in [0, 1]')
        if not isinstance(sample.get('correct'), bool):
            raise ValueError('correct must be an adjudicated boolean')

    expected = _canonical_sha256({'split': split, 'samples': samples})
    if reference.get('frozen_payload_sha256') != expected:
        raise ValueError('frozen_payload_sha256 does not match the frozen split and labels')
    return samples


def evaluate(reference: dict[str, Any], bins: int = 10) -> dict[str, Any]:
    """Calculate Brier score and equal-width expected calibration error."""
    if isinstance(bins, bool) or not isinstance(bins, int) or not 1 <= bins <= 100:
        raise ValueError('bins must be an integer from 1 through 100')
    samples = validate_reference(reference)
    n = len(samples)
    brier = sum((float(s['raw_ocr_score']) - int(s['correct'])) ** 2 for s in samples) / n
    buckets: list[list[dict[str, Any]]] = [[] for _ in range(bins)]
    for sample in samples:
        # Score 1.0 belongs to the last closed interval.
        index = min(int(float(sample['raw_ocr_score']) * bins), bins - 1)
        buckets[index].append(sample)
    bin_rows = []
    ece = 0.0
    for index, bucket in enumerate(buckets):
        count = len(bucket)
        mean_confidence = (sum(float(s['raw_ocr_score']) for s in bucket) / count) if count else None
        accuracy = (sum(s['correct'] for s in bucket) / count) if count else None
        gap = abs(mean_confidence - accuracy) if count else None
        if count:
            ece += count / n * gap
        bin_rows.append({
            'index': index,
            'lower_bound': index / bins,
            'upper_bound': (index + 1) / bins,
            'upper_bound_inclusive': index == bins - 1,
            'count': count,
            'mean_confidence': mean_confidence,
            'accuracy': accuracy,
            'absolute_gap': gap,
        })
    correct = sum(s['correct'] for s in samples)
    incorrect = n - correct
    adequate = n >= MIN_LABELS_FOR_DESCRIPTIVE_REVIEW and min(correct, incorrect) >= MIN_PER_OUTCOME_FOR_DESCRIPTIVE_REVIEW
    return {
        'schema_version': 'l2c-confidence-calibration-report-v1',
        'reference_revision': reference['revision'],
        'source_run_sha256': reference['source_run_sha256'],
        'frozen_payload_sha256': reference['frozen_payload_sha256'],
        'split': reference['split'],
        'annotator': reference['annotator'],
        'sample_count': n,
        'outcome_counts': {'correct': correct, 'incorrect': incorrect},
        'metrics': {'brier_score': brier, 'ece_equal_width': ece, 'bin_count': bins},
        'bins': bin_rows,
        'evidence_status': 'minimally_sized_descriptive_subset' if adequate else 'insufficient_labels_for_performance_claim',
        'performance_claim_permitted': False,
        'engineer_validation': 'not_performed',
        'limitations': [
            'Metrics describe only the frozen, independently declared labeled subset.',
            'This report does not establish project-wide OCR accuracy or calibrated confidence.',
            'A qualified engineer must review the references, score semantics, and results; this tool cannot attest that validation occurred.',
            'Small samples and sparse outcomes make Brier/ECE estimates unstable; no performance claim is permitted by this report.',
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path, help='Frozen local reference JSON')
    parser.add_argument('--out', required=True, type=Path, help='New report JSON path')
    parser.add_argument('--bins', type=int, default=10)
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists():
        parser.error('Choose a new output file so prior evidence is preserved.')
    try:
        reference = json.loads(args.reference.read_text(encoding='utf-8'))
        if not isinstance(reference, dict):
            raise ValueError('Reference root must be an object')
        report = evaluate(reference, args.bins)
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    report['reference_file_sha256'] = hashlib.sha256(args.reference.read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'output': str(output), 'sample_count': report['sample_count'],
                      'evidence_status': report['evidence_status'],
                      'performance_claim_permitted': False}))


if __name__ == '__main__':
    main()
