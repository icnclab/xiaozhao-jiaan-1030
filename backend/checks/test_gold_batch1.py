"""Batch 1 positive/negative rule-family regressions; no database writes."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.qa_policy import DEFAULT_POLICY, screen_risk
from app.services.qa_graph import run_graph, node_verify
from app.services.query_understanding import purchasing_rule_intent, candidate_aliases, medication_admin_intent
from app.services.retrieval_gate import assess_evidence
from app.services.answer_presentation import include_ba16_fact, assemble_answer
from app.providers.llm import CandidateAnswer
from scripts.test_retrieval_gate import chunk
from checks import test_answer_assembly as assembly_tests


class GoldBatchTests(unittest.TestCase):
    def test_disease_exclusion_family(self):
        for q in ['一直咳但沒有發燒，應該就不是肺炎吧？', '沒有發燒就可以排除感染嗎？', '這樣應該不會是骨折吧？']:
            with self.subTest(q=q):
                self.assertIn('clinical', [r.code for r in screen_risk(q)])
        for q in ['肺炎通報紀錄需要記哪些欄位？', '照服員服務紀錄怎麼填？', '可以代領藥嗎？']:
            with self.subTest(q=q):
                self.assertEqual(screen_risk(q), [])

    def test_environment_conjunction_and_negatives(self):
        for q in ['地板很濕，長輩一直走來走去', '地面積水，阿公要起身', '地板滑，住民正在行走']:
            self.assertIn('environmental_safety', [r.code for r in screen_risk(q)])
            self.assertEqual(run_graph({'question_raw': q})['reason'], 'risk_environmental_safety')
        for q in ['地板很濕，要怎麼清潔？', '地板已擦乾，长輩走來走去', '長輩自己走來走去，要填什麼服務紀錄？',
                  '地板不濕，長輩正在走動']:
            self.assertNotIn('environmental_safety', [r.code for r in screen_risk(q)])

    def test_purchasing_field_aliases_not_medication_selection(self):
        for q, expected in [('代購服務最遠可以到幾公里？','distance'), ('代領服務距離範圍是多少？','distance'),
                            ('代購的東西一定只能是長輩自己要用的嗎？','recipient'), ('代購可包含家人物品嗎？','recipient')]:
            self.assertEqual(purchasing_rule_intent(q), expected)
            self.assertTrue(candidate_aliases(q))
            self.assertFalse(medication_admin_intent(q))
            self.assertEqual(screen_risk(q), [])
        for q in ['洗澡服務最遠幾公里？', '長輩自己走路可以嗎？', '要買哪種感冒藥？']:
            self.assertIsNone(purchasing_rule_intent(q))
        self.assertIn('medication', [r.code for r in screen_risk('要買哪种感冒藥？'.replace('种','種'))])

    def test_unchanged_gate_needs_body_rule_not_title_only(self):
        q='代購服務最遠可以到幾公里？'
        appropriate=chunk('照顧組合表','代購或代領或代送服務距離自案家出門起算五公里內適用。',
                          normalized_coverage=1)
        self.assertTrue(assess_evidence(q,appropriate,DEFAULT_POLICY).admitted)
        wrong=replace(appropriate,text='員工停車位依公告申請。',coverage=.99,vector=.99,normalized_coverage=.99)
        self.assertFalse(assess_evidence(q,wrong,DEFAULT_POLICY).admitted)
        self.assertFalse(assess_evidence('代購的東西一定只能是長輩自己要用的嗎？',appropriate,DEFAULT_POLICY).admitted)

    def test_table_heading_is_verified_not_invented(self):
        h=chunk('照顧組合表','BA16 代購或代領或代送服務')
        a=replace(chunk('照顧組合表','本組合以代購或代領或代送物品為主，距離自案家出門起算五公里內。'),version_id=h.version_id)
        ids=(h.chunk_id,a.chunk_id)
        evidence={'E1':replace(h,scope_chunk_ids=ids),'E2':replace(a,scope_chunk_ids=ids)}
        c=CandidateAnswer(claims=[{'text':'距離自案家出門起算五公里內。','citation_refs':['E2']}])
        shaped=include_ba16_fact('代購服務最遠可以到幾公里？',evidence,c)
        result=node_verify(dict(question_masked='代購服務最遠可以到幾公里？',policy=DEFAULT_POLICY,
                                evidence_map=evidence,candidate=shaped))
        self.assertEqual(result['outcome'],'answer')
        self.assertEqual(result['claims'][0]['refs'],['E1'])
        self.assertIs(include_ba16_fact('代購服務最遠可以到幾公里？',{'E2':evidence['E2']},c),c)

    def test_collection_paraphrases_keep_costs_and_new_conditions(self):
        fixture=assembly_tests.AssemblyTests();fixture.setUp()
        aliases=[
            '照服員可以提供代領藥品等服務，但此組合以代購或代領或代送長照給付對象物品或事項為主。',
            '代領藥品屬於目的物品或事項之一，包括藥品。',
            '此組合的服務內容包含代購、代領或代送長照給付對象的物品或事項。',
            '若代領的物品或事項的距離超過自案家出門計算的五公里，超出部分的費用需由長照給付對象自行負擔。',
            '此服務組合以代購或代領或代送長照給付對象物品或事項為主，且適用範圍在距離自案家出門計算五公里內。',
        ]
        claims=fixture.claims + [fixture.claim(t) for t in aliases]
        rows,notice=assemble_answer('照服員可以幫長輩代領藥嗎？',fixture.evidence,claims)
        text=''.join(r['text'] for r in rows)
        for word in ['藥品','本身所需']:
            self.assertEqual(text.count(word),1)
        for word in ['五公里','自行負擔','百分之五十']:
            self.assertNotIn(word,text)
        self.assertIn('給藥',notice)
        extra=fixture.claim('代領藥品只能依機構核定的清單辦理。')
        rows,_=assemble_answer('照服員可以幫長輩代領藥嗎？',fixture.evidence,claims+[extra])
        self.assertIn(extra['text'], ''.join(r['text'] for r in rows))


if __name__=='__main__':
    unittest.main(verbosity=2)
