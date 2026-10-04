import hashlib
import json
import unittest

from scripts.evaluate_confidence_calibration import evaluate


def _digest(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def reference(count=40):
    split = {
        'name': 'test', 'independent': True,
        'independent_of': ['training', 'calibration'],
        'project_ids': ['synthetic-project'],
        'document_ids': ['synthetic-doc'],
        'frozen_at': '2026-10-04T12:00:00Z',
    }
    samples = [
        {'id': f's{i}', 'project_id': 'synthetic-project',
         'document_id': 'synthetic-doc', 'raw_ocr_score': 0.8 if i % 2 == 0 else 0.2,
         'correct': i % 2 == 0}
        for i in range(count)
    ]
    result = {
        'schema_version': 'l2c-confidence-reference-v1',
        'revision': 'synthetic-r1',
        'annotator': {'id': 'synthetic-engineer', 'qualified': True,
                      'qualification_reference': 'synthetic qualification record'},
        'source_run_sha256': hashlib.sha256(b'synthetic OCR run').hexdigest(),
        'split': split,
        'samples': samples,
    }
    result['frozen_payload_sha256'] = _digest({'split': split, 'samples': samples})
    return result


class ConfidenceCalibrationTests(unittest.TestCase):
    def test_metrics_bins_and_claim_limits(self):
        report = evaluate(reference(), bins=5)
        self.assertEqual(report['sample_count'], 40)
        self.assertAlmostEqual(report['metrics']['brier_score'], 0.04)
        self.assertAlmostEqual(report['metrics']['ece_equal_width'], 0.2)
        self.assertEqual(sum(row['count'] for row in report['bins']), 40)
        self.assertEqual(report['evidence_status'], 'minimally_sized_descriptive_subset')
        self.assertFalse(report['performance_claim_permitted'])
        self.assertEqual(report['engineer_validation'], 'not_performed')

    def test_small_label_set_has_no_performance_claim(self):
        report = evaluate(reference(count=8))
        self.assertIsNotNone(report['metrics']['brier_score'])
        self.assertEqual(report['evidence_status'], 'insufficient_labels_for_performance_claim')
        self.assertFalse(report['performance_claim_permitted'])

    def test_unqualified_or_unfrozen_reference_rejected(self):
        cases = [
            (lambda r: r.pop('annotator'), 'qualified annotator'),
            (lambda r: r['annotator'].update(qualified=False), 'qualified annotator'),
            (lambda r: r['split'].update(independent=False), 'independent'),
            (lambda r: r['split'].update(independent_of=['training']), 'independent_of'),
            (lambda r: r['split'].update(name='development'), 'test or independent_validation'),
            (lambda r: r.pop('source_run_sha256'), 'source_run_sha256'),
            (lambda r: r['samples'][0].update(correct=1), 'adjudicated boolean'),
        ]
        for change, message in cases:
            with self.subTest(message=message):
                data = reference()
                change(data)
                with self.assertRaisesRegex(ValueError, message):
                    evaluate(data)

    def test_modified_samples_fail_frozen_payload_digest(self):
        data = reference()
        data['samples'][0]['raw_ocr_score'] = 0.99
        with self.assertRaisesRegex(ValueError, 'frozen_payload_sha256'):
            evaluate(data)

    def test_sample_outside_frozen_documents_rejected_even_with_new_digest(self):
        data = reference()
        data['samples'][0]['document_id'] = 'other-document'
        data['frozen_payload_sha256'] = _digest({'split': data['split'], 'samples': data['samples']})
        with self.assertRaisesRegex(ValueError, 'frozen project/document split'):
            evaluate(data)

    def test_duplicate_ids_and_invalid_scores_rejected(self):
        data = reference()
        data['samples'][1]['id'] = data['samples'][0]['id']
        data['frozen_payload_sha256'] = _digest({'split': data['split'], 'samples': data['samples']})
        with self.assertRaisesRegex(ValueError, 'unique'):
            evaluate(data)
        data = reference()
        data['samples'][0]['raw_ocr_score'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'finite raw score'):
            evaluate(data)

    def test_one_bin_and_boundary_score_one_are_counted(self):
        data = reference(count=2)
        data['samples'][0]['raw_ocr_score'] = 1.0
        data['frozen_payload_sha256'] = _digest({'split': data['split'], 'samples': data['samples']})
        result = evaluate(data, bins=1)
        self.assertEqual(result['bins'][0]['count'], 2)
        self.assertTrue(result['bins'][0]['upper_bound_inclusive'])
