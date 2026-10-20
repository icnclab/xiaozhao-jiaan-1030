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
            self.assertEqual(body.count('五公里'), 0)
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
        self.assertEqual(body.count('五公里'), 0)
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
            item, _, _ = ask(session, SimpleNamespace(id='user', org_id='org'), question=QUESTIONS[0],
                             source='text', client_request_id='test')
        citations = [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], Citation)]
        self.assertEqual([c.label for c in citations], ['c1', 'c2'])
        self.assertEqual(item.answer_text.count('五公里'), 0)
        self.assertEqual(item.answer_text.count('用藥安全提醒'), 1)
        self.assertFalse(any('c3' in c['citations'] for c in item.claims))

    def test_service_risk_block_and_emergency_notice_unchanged(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        from app.services.qa_service import ask, EMERGENCY_NOTE
        session = MagicMock()
        session.scalar.return_value = None
        session.get.return_value = SimpleNamespace(id='org', facility_type='home')
        state = dict(outcome='escalate', reason='risk_emergency', question_masked='胸痛又喘')
        with patch('app.services.qa_service.run_graph', return_value=state), \
             patch('app.services.qa_service.load_deid_terms', return_value=[]), \
             patch('app.services.qa_service.get_llm_provider', return_value=SimpleNamespace(name='mock', model='mock')), \
             patch('app.services.quality_trace.capture', return_value={}), \
             patch('app.services.qa_service.audit.record'), \
             patch('app.services.qa_service.try_create_escalation_case', return_value=None), \
             patch('app.services.answer_presentation.assemble_answer') as assemble:
            item, _, _ = ask(session, SimpleNamespace(id='user', org_id='org'), question='胸痛又喘',
                             source='text', client_request_id='test')
        assemble.assert_not_called()
        self.assertTrue(item.answer_text.startswith(EMERGENCY_NOTE))
        self.assertEqual(item.escalation_reason, 'risk_emergency')


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
