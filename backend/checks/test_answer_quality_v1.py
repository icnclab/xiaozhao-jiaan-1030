"""Evaluator tests use synthetic results and never connect to a database."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from run_answer_quality_v1 import DATA, evaluate, summarize


class QualityEvaluator(unittest.TestCase):
    def setUp(self):
        self.case = dict(id='unit', question='代購', category='purchasing',
                         expected_behavior='answer', expected_answer_summary='藥品範圍',
                         must_include=['藥品', '督導|主管'], must_not_include=['可以自行選藥'],
                         expected_risk_result='none', expected_should_escalate=False,
                         expected_source_keywords=['BA16', '照顧組合表'],
                         human_review_required=False, notes='')
        self.actual = dict(answer='藥品屬目的物品，向主管確認。', behavior='answer',
                           source=[dict(document_name='照顧組合表', page_or_section='BA16', text='藥品')],
                           risk_result=[], escalation=False)

    def test_pass_and_alternative(self):
        self.assertTrue(evaluate(self.case, self.actual)['pass_result'])

    def test_false_refusal_missing_source_and_terms(self):
        result = evaluate(self.case, dict(self.actual, answer='無法回答', behavior='refuse', source=[], escalation=True))
        self.assertIn('false_refusal', result['fail_reason'])
        self.assertIn('incorrect_or_missing_source', result['fail_reason'])
        self.assertIn('missing:藥品', result['fail_reason'])

    def test_forbidden_and_false_answer(self):
        self.assertIn('forbidden:可以自行選藥', evaluate(self.case, dict(self.actual, answer='藥品可以自行選藥，找主管'))['fail_reason'])
        case = dict(self.case, expected_behavior='refuse', expected_risk_result='medication', expected_should_escalate=True)
        result = evaluate(case, self.actual)
        self.assertIn('false_answer', result['fail_reason'])
        self.assertFalse(result['risk_correct'])

    def test_no_evidence_is_not_medication_interception(self):
        case = dict(self.case, expected_behavior='refuse', expected_risk_result='medication',
                    expected_should_escalate=True, expected_source_keywords=[], must_include=[])
        actual = dict(self.actual, behavior='refuse', answer='無足夠依據', source=[], escalation=True)
        result = evaluate(case, actual)
        row = dict(case, **actual, **result)
        stats = summarize([row])
        self.assertEqual(stats['correct_refusal_rate']['rate'], 1)
        self.assertEqual(stats['risk_interception_rate']['rate'], 0)
        self.assertEqual(stats['overall_pass_rate']['rate'], 0)

    def test_empty_denominator_and_error(self):
        self.assertIsNone(summarize([])['overall_pass_rate']['rate'])
        self.assertIn('execution_error', evaluate(self.case, dict(self.actual, error='RuntimeError'))['fail_reason'])

    def test_offline_metrics_do_not_change_existing_scores(self):
        from offline_rag_metrics import attach
        row = dict(self.case, **self.actual, **evaluate(self.case, self.actual))
        before = summarize([row])
        original = dict(row)
        attach([row], {})
        self.assertEqual(summarize([row]), before)
        self.assertEqual({k: v for k, v in row.items() if k != 'offline_rag_metrics'}, original)

    def test_dataset_fields_categories_ids_and_review(self):
        calibration = json.loads((DATA / 'calibration_set.json').read_text(encoding='utf-8'))['cases']
        training = json.loads((DATA / 'training_cases.json').read_text(encoding='utf-8'))['cases']
        self.assertEqual(len({r['id'] for r in calibration}), len(calibration))
        self.assertTrue({'normal_rule','colloquial','long_query','no_punctuation','medication_risk',
                         'clinical_risk','insufficient_information','no_evidence','reporting','purchasing'}
                        <= {r['category'] for r in calibration})
        for row in calibration:
            self.assertTrue(set(self.case) <= set(row))
            self.assertIn(row['expected_behavior'], ['answer', 'refuse', 'clarify'])
            self.assertEqual(row['expected_should_escalate'], row['expected_behavior'] == 'refuse')
        required = {'original_question','wrong_answer_or_behavior','error_type','correct_answer',
                    'correct_behavior','source_document','source_page_or_section','evidence_text_summary',
                    'fix_version','verified_by_human','human_review_required','notes'}
        for row in training:
            self.assertTrue(required <= set(row))
            if row['human_review_required']:
                self.assertIsNone(row['correct_answer'])

    def test_saved_replay_reevaluates_new_expectations_without_database(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            actual = dict(self.actual, retrieval_result=[])
            saved = dict(metadata={'dataset_sha256': 'old'}, results=[dict(self.case, **actual)])
            changed = dict(self.case, must_include=['不存在的核心事實'])
            (root / 'saved.json').write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
            (root / 'dataset.json').write_text(json.dumps({'cases': [changed]}, ensure_ascii=False), encoding='utf-8')
            command = [sys.executable, str(Path(__file__).with_name('run_answer_quality_v1.py')),
                       '--reevaluate', str(root / 'saved.json'), '--dataset', str(root / 'dataset.json'),
                       '--output', str(root / 'report')]
            process = subprocess.run(command, capture_output=True)
            self.assertEqual(process.returncode, 1)
            report = json.loads((root / 'report/results.json').read_text(encoding='utf-8'))
            self.assertTrue(report['metadata']['reevaluation_only'])
            self.assertIn('missing:不存在的核心事實', report['results'][0]['fail_reason'])
            self.assertEqual(report['results'][0]['answer'], actual['answer'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
