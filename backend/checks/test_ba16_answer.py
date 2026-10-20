"""BA16 wording regression; real DB/LLM replay uses READ ONLY transaction."""
import sys
import unittest
import uuid
from datetime import date
from dataclasses import replace

from app.providers.llm import CandidateAnswer
from app.services.answer_presentation import include_ba16_fact, ba16_safety_note
from app.services.qa_graph import node_verify, run_graph
from app.services.qa_policy import DEFAULT_POLICY, screen_risk
from scripts.test_retrieval_gate import chunk

QUESTION = '家屬叫我順便幫長輩買成藥，這個可以嗎？'


class AnswerWording(unittest.TestCase):
    def setUp(self):
        header = chunk('附表四 照顧組合表', 'BA16 代購或代領或代送服務')
        obj = replace(chunk('附表四 照顧組合表', '一、目的物品或事項包括：餐食、食材、生活用品、藥品、郵寄、補助品。'),
                      version_id=header.version_id)
        ids = (header.chunk_id, obj.chunk_id)
        self.evidence = {'E1': replace(header, scope_chunk_ids=ids), 'E2': replace(obj, scope_chunk_ids=ids)}

    def test_core_fact_survives_existing_verifier(self):
        c = CandidateAnswer(claims=[{'text':'代購或代領或代送的服務內容包含藥品。','citation_refs':['E2']}])
        shaped = include_ba16_fact(QUESTION, self.evidence, c)
        state = dict(question_masked=QUESTION, policy=DEFAULT_POLICY, candidate=shaped, evidence_map=self.evidence)
        result = node_verify(state)
        self.assertEqual(result['outcome'], 'answer')
        self.assertIn('藥品', result['claims'][0]['text'])
        self.assertEqual(result['claims'][0]['refs'], ['E1','E2'])
        self.assertGreaterEqual(result['claims'][0]['support'], DEFAULT_POLICY.min_support)
        self.assertIn('用藥安全提醒', ba16_safety_note(QUESTION,self.evidence,result['claims']))

    def test_no_source_no_assertion_and_other_topics_unchanged(self):
        c = CandidateAnswer(claims=[{'text':'原答案','citation_refs':['E2']}])
        for evidence, question in [(self.evidence,'沐浴服務可以嗎？'), ({'E2':self.evidence['E2']},QUESTION)]:
            self.assertIs(include_ba16_fact(question,evidence,c),c)
            self.assertEqual(ba16_safety_note(question,evidence,[]),'')
        cross = dict(self.evidence,E1=replace(self.evidence['E1'],version_id=uuid.uuid4()))
        self.assertIs(include_ba16_fact(QUESTION,cross,c),c)

    def test_human_conflict_and_empty_flags_preserved(self):
        for c in [CandidateAnswer(needs_human=True),CandidateAnswer(conflict=True),
                  CandidateAnswer(raw_ok=False),CandidateAnswer()]:
            self.assertIs(include_ba16_fact(QUESTION,self.evidence,c),c)


def replay():
    from sqlalchemy import create_engine, text, select
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from app.config import get_settings
    from app.models import Organization
    url = make_url(get_settings().database_url)
    assert url.database == 'ltc_clean'
    questions = [QUESTION, '可以幫忙買藥嗎？', '要買哪一種感冒藥？', '買回來吃幾顆？', '可以直接幫他餵藥嗎？']
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text('SET TRANSACTION READ ONLY'))
            session = Session(bind=connection)
            org = session.scalar(select(Organization).where(Organization.code=='JIAAN'))
            for index,q in enumerate(questions):
                result = run_graph(dict(question_raw=q,session=session,org_id=org.id,
                                        facility_type=org.facility_type,today=date(2026,10,11)))
                print('RESULT',q,result.get('outcome'),result.get('reason'),flush=True)
                if index < 2:
                    assert result['outcome']=='answer', result.get('reason')
                    claims=result['claims']
                    assert any('藥品' in c['text'] for c in claims)
                    assert any('本身所需' in c['text'] for c in claims)
                    assert any('五公里' in c['text'] for c in claims)
                    note=ba16_safety_note(q,result['evidence_map'],claims)
                    assert '自行決定' in note and '醫療專業人員' in note
                    print('ANSWER',''.join(c['text'] for c in claims)+note,flush=True)
                else:
                    assert result['outcome']!='answer', result.get('claims')
                    print('RISK_RULE_MATCH',[rule.code for rule in screen_risk(q)],flush=True)
                    if index==3:
                        assert result['reason']=='risk_medication'
            session.close()
            connection.rollback()
    finally:
        engine.dispose()


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AnswerWording))
    if not result.wasSuccessful():raise SystemExit(1)
    if '--replay' in sys.argv:replay()
