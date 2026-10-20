"""Pure regression tests: no DB, LLM, or running service."""
import unittest
from datetime import date
from unittest.mock import patch
from app.services import qa_graph
from app.services.retrieval_gate import assess_evidence
from scripts.test_retrieval_gate import chunk
from app.services.qa_policy import screen_risk, DEFAULT_POLICY
from app.services.qa_graph import node_screen_risk, node_clarify
from app.services.query_understanding import (medication_admin_intent, permission_intent,
    topic_token_groups, contextual_question, normalize_colloquial)


class MedicationIntent(unittest.TestCase):
    def test_administrative_evidence_requires_topical_rule(self):
        q = '家屬要我代購成藥可以嗎？'
        good = chunk('代購服務規範', '照服員提供代購服務應依服务契約辦理。', coverage=.7, vector=.6)
        bad = chunk('代購服務規範', '照服員提供沐浴服務應依服务契約辦理。', coverage=.7, vector=.6)
        self.assertTrue(assess_evidence(q, good, DEFAULT_POLICY).admitted)
        self.assertFalse(assess_evidence(q, bad, DEFAULT_POLICY).admitted)
    def test_administrative_questions_reach_retrieval(self):
        for q in ['家屬要我代購成藥可以嗎？', '家屬要我代購成藥可以嗎',
                  '家屬要我代購成藥 可以嗎', '家屬叫我幫忙買成藥', '可以幫長輩領藥嗎']:
            with self.subTest(q=q):
                state = {'question_masked':normalize_colloquial(q), 'policy':DEFAULT_POLICY}
                self.assertTrue(medication_admin_intent(q))
                self.assertTrue(permission_intent(q))
                self.assertFalse(screen_risk(q))
                self.assertNotIn('outcome', node_screen_risk(state))
                self.assertNotIn('outcome', node_clarify(state))
                self.assertTrue(topic_token_groups(q))
                with patch.object(qa_graph, 'node_retrieve', return_value={'outcome':'escalate', 'reason':'no_evidence'}) as retrieval:
                    result = qa_graph.build_graph().invoke(dict(question_raw=q, policy=DEFAULT_POLICY,
                        session=None, org_id=None, facility_type='home', today=date(2026, 10, 9)))
                retrieval.assert_called_once()
                self.assertEqual(result['reason'], 'no_evidence')

    def test_clinical_questions_still_blocked(self):
        for q in ['家屬留下來的藥可以直接給長輩吃嗎？', '這個藥一次要吃幾顆？',
                  '長輩胸痛可以先吃什麼藥？', '可以多給一次藥嗎？',
                  '長輩突然胸痛又喘，可以先給家屬留下來的藥嗎？',
                  '家屬叫我買藥，這個藥要吃幾顆？', '藥物副作用',
                  '胸\n痛可以先吃什麼藥', '劑量多少', '可以多吃一次嗎？']:
            with self.subTest(q=q):
                self.assertTrue(screen_risk(normalize_colloquial(q)))
                with patch.object(qa_graph, 'node_retrieve', side_effect=AssertionError('risk reached retrieval')):
                    result = qa_graph.build_graph().invoke(dict(question_raw=q, policy=DEFAULT_POLICY,
                        session=None, org_id=None, facility_type='home', today=date(2026, 10, 9)))
                self.assertEqual(result['outcome'], 'escalate')

    def test_short_followup_needs_explicit_safe_context(self):
        q = '可以代買嗎'
        self.assertEqual(contextual_question(q, None), q)
        state = {'question_masked':q, 'policy':DEFAULT_POLICY}
        self.assertEqual(node_clarify(state)['outcome'], 'clarify')
        self.assertIn('代購成藥', contextual_question(q, '家屬要我代購成藥可以嗎'))
        self.assertEqual(contextual_question(q, '長輩胸痛要買藥'), q)
        self.assertEqual(contextual_question(q, '這個可以嗎'), q)

    def test_long_query_preserves_risk_and_core_action(self):
        q = '我想請問，家屬剛剛來找我\n家屬要我代購成藥 可以嗎'
        self.assertTrue(medication_admin_intent(normalize_colloquial(q)))
        self.assertEqual(len(topic_token_groups(q)), 1)
        self.assertTrue(screen_risk(normalize_colloquial(q + '，長輩胸痛')))


if __name__ == '__main__':
    unittest.main()
