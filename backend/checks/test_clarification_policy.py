"""No DB/LLM calls: versioned missing-operation policy and graph routing."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.qa_policy import DEFAULT_POLICY, clarification_decision
from app.services.qa_graph import node_clarify, run_graph

POSITIVE = [
    '家屬說以前都這樣做，所以今天照做就可以吧？',
    '這樣做可以嗎？',
    '家屬說以前都這樣，今天也可以吧？',
    '今天照以前做可以吧？',
    '還是照原本做就好？',
    '家屬叫照服員照原本的方式服務就好，可以嗎？',
]
NEGATIVE = [
    '以前都這樣幫長輩洗澡，今天照做可以嗎？',
    '家屬要求更換尿布，照以前做可以嗎？',
    '照原本做早餐可以嗎？',
    '可以幫忙買藥嗎？',
    '家屬說以前都這樣代領藥，今天可以照做嗎？',
    '還是照原本做清潔地板就好？',
    '以前都這樣填服務紀錄，照做可以嗎？',
    '以前都這樣推輪椅，今天照做可以嗎？',
]
RISK = [
    ('長輩胸痛又喘，家屬說以前都這樣做，照做可以吧？', 'risk_emergency'),
    ('長輩跌倒撞到頭，還是照原本做？', 'risk_fall_head_impact'),
    ('異常嗜睡叫不醒，照以前做嗎？', 'risk_emergency'),
    ('要買哪種感冒藥，家屬說以前都這樣做？', 'risk_medication'),
]


class ClarificationPolicyTests(unittest.TestCase):
    def test_positives_skip_rag_and_llm(self):
        for q in POSITIVE:
            with self.subTest(question=q), patch('app.services.qa_graph.retrieve') as retrieval, \
                 patch('app.services.qa_graph.get_llm_provider') as llm:
                result = run_graph({'question_raw': q, 'policy': DEFAULT_POLICY})
                self.assertEqual(result['outcome'], 'clarify')
                self.assertEqual(result['reason'], 'need_context')
                trace = result['checks']['clarification']
                self.assertEqual(trace['rule_code'], 'unspecified_repeated_operation')
                self.assertEqual(trace['policy_version'], '2026-10-11.clarification.1')
                self.assertIn('請先說明家屬希望照服員做什麼', trace['prompt'])
                self.assertFalse(result['risk_codes'])
                retrieval.assert_not_called()
                llm.assert_not_called()

    def test_concrete_operations_not_clarified(self):
        for q in NEGATIVE:
            with self.subTest(question=q):
                result = node_clarify(dict(question_masked=q, policy=DEFAULT_POLICY))
                self.assertNotEqual(result.get('outcome'), 'clarify')

    def test_risk_has_priority_and_never_enters_rag(self):
        for q, reason in RISK:
            with self.subTest(question=q), patch('app.services.qa_graph.retrieve') as retrieval:
                result = run_graph({'question_raw': q, 'policy': DEFAULT_POLICY})
                self.assertEqual(result['outcome'], 'escalate')
                self.assertEqual(result['reason'], reason)
                self.assertNotIn('clarification', result['checks'])
                retrieval.assert_not_called()

    def test_no_actor_only_bypass_and_unrelated_rules_unchanged(self):
        self.assertTrue(clarification_decision('家屬說照以前做就好，照服員可以嗎？')['needed'])
        self.assertIsNone(clarification_decision('長照服務費用如何計算？'))
        legacy = node_clarify(dict(question_masked='他今天怪怪的，我要怎麼辦？', policy=DEFAULT_POLICY))
        self.assertEqual(legacy['outcome'], 'clarify')

    def test_feedback_trace_includes_policy_and_decision(self):
        from datetime import date
        from app.services.quality_trace import capture
        state = run_graph({'question_raw': POSITIVE[0], 'policy': DEFAULT_POLICY})
        state.update(today=date(2026, 10, 11), policy=DEFAULT_POLICY)
        trace = capture(state)
        self.assertEqual(trace['qa_policy_version'], '2026-10-12.systematic.1')
        self.assertEqual(trace['clarification_policy_version'], '2026-10-11.clarification.1')
        self.assertTrue(trace['clarification_result']['needed'])
        self.assertFalse(trace['retrieval_executed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
