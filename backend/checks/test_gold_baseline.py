"""Offline metric semantics only; no DB or graph execution."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from checks.evaluate_gold_v1 import assess, metric, statistics


def record(behavior, basis='system_safety_policy', answer='請補充具體操作。'):
    return dict(id='feedback', qa_snapshot={'question':'測試'}, reviewed_correction=dict(
        expected_behavior=behavior, error_type='incomplete_answer', correct_answer=answer,
        evidence_basis_type=basis, correct_source_document='附表四 照顧組合表',
        correct_source_page_or_section='第 14 頁，BA16'))


def actual(outcome, risk=None):
    return dict(outcome=outcome, risk_result=risk or [], behavior='refuse', answer='請補充具體操作。', source=[])


class GoldBaselineTests(unittest.TestCase):
    def test_no_evidence_is_not_risk_block(self):
        row=assess(record('risk_block'),actual('escalate'),{})
        self.assertFalse(row['risk_block_recalled'])
        self.assertEqual(row['actual_behavior'],'escalate')

    def test_actual_risk_counts_recall(self):
        row=assess(record('risk_block'),actual('escalate',['medication']),{})
        self.assertTrue(row['risk_block_recalled'])
        self.assertIsNone(row['citation_correctness_proxy'])

    def test_false_refusal_and_missing_sources(self):
        row=assess(record('direct_answer','official_kb_document'),actual('escalate'),{})
        self.assertTrue(row['false_refusal'])
        self.assertFalse(row['citation_correctness_proxy'])

    def test_clarification_excluded_from_answer_denominator(self):
        rows=[assess(record('clarify'),actual('clarify'),{}),
              assess(record('answer'),actual('escalate'),{})]
        stats=statistics(rows)
        self.assertEqual(stats['answer_correctness_proxy']['denominator'],1)
        self.assertEqual(stats['clarification_match']['numerator'],1)

    def test_offline_metrics_do_not_change_gold_scores(self):
        from checks.offline_rag_metrics import attach
        row = assess(record('answer'), actual('escalate'), {})
        before = statistics([row])
        original = dict(row)
        attach([row], {})
        self.assertEqual(statistics([row]), before)
        self.assertEqual({k: v for k, v in row.items() if k != 'offline_rag_metrics'}, original)
        self.assertIsNone(row['offline_rag_metrics']['faithfulness']['rate'])

    def test_not_applicable_is_not_zero(self):
        self.assertIsNone(metric([None])['rate'])
        self.assertEqual(metric([False])['rate'],0)


if __name__=='__main__':
    unittest.main(verbosity=2)
