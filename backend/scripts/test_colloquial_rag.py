"""Generalized colloquial/action/intent regressions, no production DB writes."""
import sys
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_retrieval_gate import chunk
from app.services import qa_graph
from app.services.retrieval_gate import assess_evidence
from app.services.retrieval import _topic_token_groups, _topic_match, _expand_query
from app.services.query_understanding import permission_intent, reporting_intent, clarification_reason
from app.services.text import bigrams
from app.services.qa_policy import DEFAULT_POLICY


class ColloquialTests(unittest.TestCase):
    def assess(self, q, text, title='相關規範疑義', **kwargs):
        c = chunk(title, text, **kwargs)
        c = replace(c, normalized_coverage=1.0)
        return assess_evidence(q, c, DEFAULT_POLICY)

    def test_dressing_permission_preserved(self):
        self.assertTrue(self.assess('我可以幫他換藥嗎？', '一般傷口更換敷料難謂無涉醫療專業判斷。', '傷口換藥疑義').admitted)

    def test_cleaning_variants_use_full_action_not_actor(self):
        for q in ('照服員可以幫忙清傷口嗎？', '照顧服務員可否清潔傷口？',
                  '可以幫長輩清洗傷口嗎？', '傷口清潔能不能做？'):
            with self.subTest(q=q):
                self.assertTrue(self.assess(q, '一般傷口更換敷料、傷口簡易清潔等情，難謂無涉醫療專業判斷。', '傷口換藥疑義').admitted)
                self.assertFalse(self.assess(q, '照服員服務範圍不得涉及護理行為。', '傷口換藥疑義').admitted)

    def test_unrelated_cleaning_not_wound_expansion(self):
        for q in ('可以清潔桌面嗎？', '幫他清洗衣物可以嗎？'):
            self.assertNotIn('傷口簡易清潔', _expand_query(q, date(2026, 10, 8)))
            self.assertFalse(self.assess(q, '傷口簡易清潔難謂无涉醫療專業判斷。').admitted)

    def test_ambiguous_actions_across_objects_clarify(self):
        for q in ('這個傷口我可以自己處理嗎？', '那個管路我能自己處理嗎？', '這個紀錄可以這樣弄嗎？'):
            self.assertEqual(clarification_reason(q), 'unspecified_action')
            self.assertTrue(qa_graph._needs_clarification(q))

    def test_concrete_action_not_clarified_just_for_pointer(self):
        for q in ('這個傷口可以換藥嗎？', '那個長輩要不要回報跌倒？', '這個照服員可否協助翻身？'):
            self.assertFalse(qa_graph._needs_clarification(q))

    def test_pronoun_only_clarifies(self):
        for q in ('這個可以嗎？', '那個能不能做？'):
            self.assertTrue(qa_graph._needs_clarification(q))

    def test_unknown_specific_subject_not_guessed(self):
        q = '可以提供火星基地量子護盾校準服務嗎？'
        self.assertFalse(qa_graph._needs_clarification(q))
        self.assertFalse(self.assess(q, '照服員應依服務範圍提供服務。').admitted)

    def test_reporting_does_not_need_receiver(self):
        a = _topic_token_groups('長輩跌倒要不要回報？')
        b = _topic_token_groups('跌倒要不要回報督導？')
        self.assertEqual(a, b)
        for q in ('長輩跌倒要不要回報？', '跌倒要不要回報督導？', '阿公跌倒可以通報嗎？'):
            self.assertTrue(reporting_intent(q))
            self.assertFalse(permission_intent(q))
            self.assertTrue(self.assess(q, '跌倒後應向主管通報，完整記錄事發經過。').admitted)

    def test_reporting_false_cooccurrence_rejected(self):
        text = '應回報工作進度。移位技巧有助於預防跌倒。'
        self.assertEqual(self.assess('跌倒要不要回報？', text).reason, 'reporting_rule_missing')

    def test_other_incident_reporting(self):
        for event in ('燙傷', '走失', '失蹤'):
            q = f'長輩{event}要不要回報？'
            self.assertTrue(self.assess(q, f'發生{event}事件須通報主管。').admitted)

    def test_scope_boundary_rule_not_contract_definition(self):
        q = '家屬叫我做服務計畫外的事情，可以嗎？'
        self.assertTrue(self.assess(q, '照服員應維持清楚角色界線，回歸服務契約書之規定項目。').admitted)
        self.assertFalse(self.assess(q, '長照機構應簽訂服務契約，列明費用。').admitted)

    def test_scope_case_description_not_rule(self):
        q = '家屬叫我做服務計畫外的事情，可以嗎？'
        self.assertFalse(self.assess(q, '家屬要求非服務項目內的工作，照服員默默配合，未能堅持合理服務範圍。').admitted)

    def test_specialized_service_not_generalized(self):
        q = '家屬叫我做服務計畫外的事情，可以嗎？'
        self.assertEqual(self.assess(q, 'BA05 不得因家屬要求超出服務範圍。').reason, 'specific_service_scope_not_requested')

    def test_high_normalized_score_cannot_bypass_permission_rule(self):
        self.assertFalse(self.assess('照服員可以幫忙清傷口嗎？', '傷口簡易清潔操作步驟如下。', coverage=1, vector=0.99).admitted)

    def test_high_normalized_score_cannot_bypass_context(self):
        self.assertEqual(self.assess('這個傷口我可以自己處理嗎？', '傷口處理不得涉及醫療行為。').reason, 'needs_clarification')

    def test_graph_risk_precedes_clarify(self):
        for q in ('這個傷口感染要不要送醫？', '這個長輩叫不醒怎麼辦？', '安眠藥可以多給半顆嗎？'):
            with patch.object(qa_graph, 'node_clarify') as clarify, patch.object(qa_graph, 'retrieve') as retrieve:
                state = qa_graph.build_graph().invoke({'session': None, 'question_raw': q,
                    'org_id': uuid.uuid4(), 'facility_type': 'home', 'today': date(2026, 10, 8),
                    'policy': DEFAULT_POLICY})
            self.assertEqual(state['outcome'], 'escalate')
            self.assertTrue(state['reason'].startswith('risk_'))
            clarify.assert_not_called()
            retrieve.assert_not_called()

    def test_graph_clarify_does_not_retrieve_or_generate(self):
        for q in ('這個傷口我可以自己處理嗎？', '這個可以嗎？'):
            with patch.object(qa_graph, 'retrieve') as retrieve, patch.object(qa_graph, 'get_llm_provider') as provider:
                state = qa_graph.run_graph({'session': None, 'question_raw': q, 'org_id': uuid.uuid4(),
                    'facility_type': 'home', 'today': date(2026, 10, 8)})
            self.assertEqual(state['outcome'], 'clarify')
            self.assertTrue(state['checks']['clarification']['prompt'])
            retrieve.assert_not_called()
            provider.assert_not_called()


if __name__ == '__main__':
    unittest.main()
