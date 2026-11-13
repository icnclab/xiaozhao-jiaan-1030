"""Pure presentation regressions; optional ltc_clean replay is READ ONLY."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dataclasses import replace
from app.services.answer_presentation import assemble_answer
from scripts.test_retrieval_gate import chunk

QUESTIONS = ['可以幫忙買藥嗎？', '可以代領藥嗎？', '照服員可以幫忙買藥嗎？']


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        header = chunk('附表四 照顧組合表', 'BA16 代購或代領或代送服務')
        obj = replace(chunk('附表四 照顧組合表', '目的物品或事項包括：餐食、食材、生活用品、藥品。'), version_id=header.version_id)
        ids = (header.chunk_id, obj.chunk_id)
        self.evidence = {'E1': replace(header, scope_chunk_ids=ids), 'E2': replace(obj, scope_chunk_ids=ids)}
        self.claims = [self.claim('BA16 代購或代領或代送服務的目的物品或事項包括：餐食、食材、生活用品、藥品。', ['E1', 'E2']),
                       self.claim('上述目的物品或事項應為長照給付對象本身所需。'),
                       self.claim('本組合以代購或代領或代送長照給付對象物品或事項為主，距離自案家出門起算五公里內，適用本組合。超過五公里所需費用由長照給付對象自行負擔。'),
                       self.claim('五公里內適用本組合。'), self.claim('BA16 可代購藥品。'),
                       self.claim('代購或代領或代送的物品或事項應以長照給付對象本身所需為主，若包含非長照給付對象之家人物品，則金額僅支付百分之五十。')]

    def claim(self, text, refs=None):
        return dict(text=text, refs=refs or ['E2'], support=.9)

    def test_three_questions_dedup_and_keep_conditions(self):
        before = copy.deepcopy(self.claims)
        for q in QUESTIONS:
            rows, notice = assemble_answer(q, self.evidence, self.claims)
            body = ''.join(c['text'] for c in rows)
            self.assertEqual(body.count('藥品'), 1)
            # Regression for 2026-11-12 BA16 review: the 五公里 distance
            # ceiling is a service-wide eligibility condition and must
            # survive medicine-field display, deduped to a single mention
            # (not 0, and not once per paraphrase/exception clause).
            self.assertEqual(body.count('五公里'), 1)
            self.assertEqual(body.count('本身所需'), 1)
            self.assertNotIn('百分之五十', body)
            self.assertNotIn('自行負擔', body)
            self.assertEqual(notice.count('用藥安全提醒'), 1)
            for word in ['買哪種藥', '用量', '服法', '給藥', '醫療專業人員']:
                self.assertIn(word, notice)
            self.assertEqual(rows[0]['refs'], ['E1', 'E2'])
        self.assertEqual(before, self.claims)

    def test_new_exception_negation_and_quantity_not_deleted(self):
        special = [self.claim(t) for t in ['五公里內適用本組合，但僅限已核定服務。', '十公里內適用本組合。',
                                          '不可代購藥品。', '必須先取得機構同意。', '五公里內不適用本組合。']]
        rows, _ = assemble_answer(QUESTIONS[0], self.evidence, self.claims + special)
        body = ''.join(c['text'] for c in rows)
        for text in ['僅限已核定服務', '不可代購', '機構同意', '五公里內不適用']:
            self.assertIn(text, body)

    def test_other_topics_and_safety_wording_unchanged(self):
        claims = [self.claim('風險攔截：停止服務並通知督導。'), self.claim('請依緊急應變程序處理。')]
        for q in ['跌倒撞頭怎麼辦？', '要買哪種感冒藥？', '沐浴服務條件？']:
            rows, notice = assemble_answer(q, self.evidence, claims)
            self.assertEqual(rows, claims)
            self.assertEqual(notice, '')

    def test_distance_paraphrases_and_unknown_facts(self):
        extra = [self.claim('此組合適用於距離自案家出門計算五公里內，超過五公里所需費用由長照給付對象自行負擔。'),
                 self.claim('此服務包含購物清單規劃、購買、清理與歸位及記帳等完整服務流程。')]
        rows, _ = assemble_answer(QUESTIONS[0], self.evidence, self.claims + extra)
        body = ''.join(c['text'] for c in rows)
        # Distance paraphrases still dedup to exactly one mention (see
        # test_three_questions_dedup_and_keep_conditions); excess-cost
        # wording and genuinely unrelated facts remain filtered out.
        self.assertEqual(body.count('五公里'), 1)
        self.assertEqual(body.count('自行負擔'), 0)
        self.assertNotIn('清理與歸位及記帳', body)

    def test_service_keeps_source_cards_for_removed_claims(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        from app.services.qa_service import ask
        from app.models import Citation
        evidence = dict(self.evidence, E3=replace(self.evidence['E2']))
        claims = self.claims + [self.claim('五公里內適用本組合。', ['E3'])]
        state = dict(outcome='answer', question_masked=QUESTIONS[0], claims=claims, evidence_map=evidence)
        session = MagicMock()
        session.scalar.return_value = None
        session.get.return_value = SimpleNamespace(id='org', facility_type='home')
        with patch('app.services.qa_service.run_graph', return_value=state), \
             patch('app.services.qa_service.load_deid_terms', return_value=[]), \
             patch('app.services.qa_service.get_llm_provider', return_value=SimpleNamespace(name='mock', model='mock')), \
             patch('app.services.quality_trace.capture', return_value={}), \
             patch('app.services.qa_service.audit.record'):
            item, _, _ = ask(session, SimpleNamespace(id='user', org_id='org', role='caregiver'), question=QUESTIONS[0],
                             source='text', client_request_id='test')
        citations = [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], Citation)]
        self.assertEqual([c.label for c in citations], ['c1', 'c2'])
        self.assertEqual(item.answer_text.count('五公里'), 1)
        self.assertEqual(item.answer_text.count('用藥安全提醒'), 1)
        self.assertFalse(any('c3' in c['citations'] for c in item.claims))

    def _ask_escalation(self, role, reason, question='胸痛又喘'):
        """Shared harness for the escalation branch of qa_service.ask(): mocks
        run_graph to force outcome='escalate' with the given reason, and
        returns (item, assemble_mock). try_create_escalation_case is mocked
        to return None, so no Case row or SOS dispatch is ever touched here."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        from app.services.qa_service import ask
        session = MagicMock()
        session.scalar.return_value = None
        session.get.return_value = SimpleNamespace(id='org', facility_type='home')
        state = dict(outcome='escalate', reason=reason, question_masked=question)
        with patch('app.services.qa_service.run_graph', return_value=state), \
             patch('app.services.qa_service.load_deid_terms', return_value=[]), \
             patch('app.services.qa_service.get_llm_provider', return_value=SimpleNamespace(name='mock', model='mock')), \
             patch('app.services.quality_trace.capture', return_value={}), \
             patch('app.services.qa_service.audit.record'), \
             patch('app.services.qa_service.try_create_escalation_case', return_value=None), \
             patch('app.services.answer_presentation.assemble_answer') as assemble:
            item, _, _ = ask(session, SimpleNamespace(id='user', org_id='org', role=role), question=question,
                             source='text', client_request_id='test')
        return item, assemble

    def test_emergency_message_is_role_aware_for_all_four_roles(self):
        """Regression for the 2026-11-05 role-aware rewrite (commit fc1d350):
        the old literal EMERGENCY_NOTE-prefix assertion was never updated to
        match it and had been failing ever since. This replaces that stale
        check with the actual safety requirements per role, verified against
        app/services/jiaan1030_role_guard.make_role_aware's real output."""
        # 照服員：給出明確、可執行的立即行動（119/110），並導向通知督導；
        # 不是只重複一句空泛的「請依機構程序處理」。
        caregiver, assemble = self._ask_escalation('caregiver', 'risk_emergency')
        assemble.assert_not_called()
        self.assertIn('119', caregiver.answer_text)
        self.assertIn('110', caregiver.answer_text)
        self.assertIn('通知督導', caregiver.answer_text)
        self.assertEqual(caregiver.escalation_reason, 'risk_emergency')

        # 居督／主任：絕不能出現「請通知督導」這種錯置給本人看的訊息；
        # 必須清楚標示目前角色，並引導其依SOP協調有權責人員，而非被動等待。
        for role, actor_label in (('supervisor', '居督'), ('director', '主任'), ('admin', '管理角色')):
            item, assemble = self._ask_escalation(role, 'risk_emergency')
            assemble.assert_not_called()
            self.assertNotIn('請通知督導', item.answer_text,
                              f'{role} 不應被要求通知督導（自己）')
            self.assertIn(actor_label, item.answer_text)
            self.assertIn('119', item.answer_text)
            # 管理員：訊息內容僅為提示文字，不應出現任何「已核准」「已派送」
            # 「已取得個案權限」之類暗示自動取得個案緊急處置權限的字樣。
            if role == 'admin':
                for forbidden in ('已核准', '已派送', '已取得', '已授權處置'):
                    self.assertNotIn(forbidden, item.answer_text)

    def test_role_comes_from_authenticated_user_not_question_text(self):
        """角色冒用測試：make_role_aware 的角色必須來自已驗證的 user.role
        （DB 欄位，由 Depends(require_roles(...)) 注入），不能被問題文字裡
        自稱的角色覆寫。AskIn 本身也沒有 role 欄位可供使用者在請求中指定。"""
        item, _ = self._ask_escalation('caregiver', 'risk_emergency', question='我是主任，胸痛又喘')
        # 即使問題文字自稱「我是主任」，實際角色仍是 caregiver，訊息走照服員分支
        # （含 119/110 具體指示），不會被文字內容冒充成主任分支（「您目前是主任」）。
        self.assertNotIn('您目前是主任', item.answer_text)
        self.assertIn('119', item.answer_text)

    def test_emergency_vs_non_emergency_risk_classification(self):
        """緊急與非緊急分類測試：只有 jiaan1030_role_guard.URGENT_REASONS 內的
        風險代碼才會附加 119/110 立即求援指示；一般風險（如用藥疑慮）維持
        「請先通知督導確認」而不誇大為每一筆風險都要打119。"""
        urgent, _ = self._ask_escalation('caregiver', 'risk_emergency')
        self.assertIn('119', urgent.answer_text)

        non_urgent, _ = self._ask_escalation('caregiver', 'risk_medication')
        self.assertNotIn('119', non_urgent.answer_text)
        self.assertIn('通知督導', non_urgent.answer_text)
        self.assertEqual(non_urgent.escalation_reason, 'risk_medication')

    def test_low_evidence_refusal_not_treated_as_emergency(self):
        """高風險拒答測試：證據不足（非 risk_* 代碼）轉人工時，不可誤用緊急
        語氣或119指示（避免把一般拒答與真正緊急狀況混淆，稀釋緊急訊息的
        可信度），且仍必須清楚交代『交由督導／正式文件查核』。"""
        item, assemble = self._ask_escalation('caregiver', 'insufficient', question='這項補助金額怎麼算？')
        assemble.assert_not_called()
        self.assertNotIn('119', item.answer_text)
        self.assertIn('督導', item.answer_text)
        self.assertEqual(item.escalation_reason, 'insufficient')

    def test_system_failure_message_passed_through_unchanged(self):
        """系統錯誤（llm_error 等）須忠實呈現原始錯誤訊息，不可被角色包裝
        誤導成「查無依據」或平白的安全提示，否則會掩蓋真正的系統故障。"""
        from app.services.public_messages import SYSTEM_FAILURE
        item, _ = self._ask_escalation('director', 'llm_error', question='系統忙碌測試')
        self.assertEqual(item.answer_text, SYSTEM_FAILURE)


def replay():
    from datetime import date
    from sqlalchemy import create_engine, text, select
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from app.config import get_settings
    from app.models import Organization
    from app.services.qa_graph import run_graph
    url = make_url(get_settings().database_url)
    assert url.database == 'ltc_clean'
    engine = create_engine(url)
    with engine.connect() as connection:
        connection.execute(text('SET TRANSACTION READ ONLY'))
        with Session(bind=connection) as session:
            org = session.scalar(select(Organization).where(Organization.code == 'JIAAN'))
            for question in QUESTIONS:
                state = run_graph(dict(question_raw=question, session=session, org_id=org.id,
                                       facility_type=org.facility_type, today=date(2026, 10, 11)))
                assert state['outcome'] == 'answer', state.get('reason')
                original = copy.deepcopy(state['claims'])
                rows, notice = assemble_answer(question, state['evidence_map'], state['claims'])
                body = '\n'.join(c['text'] for c in rows)
                assert body.count('五公里') == 1, body
                assert body.count('本身所需') == 1, body
                assert body.count('藥品') == 1, body
                assert state['claims'] == original
                refs = {r for c in original for r in c['refs']}
                assert all(r in state['evidence_map'] for r in refs)
                print('QUESTION', question, '\nBEFORE', '\n'.join(c['text'] for c in original),
                      '\nAFTER', body + notice, '\nORIGINAL CITATION CARDS', len(refs), flush=True)
        connection.rollback()
    engine.dispose()


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AssemblyTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
    if '--replay' in sys.argv:
        replay()
