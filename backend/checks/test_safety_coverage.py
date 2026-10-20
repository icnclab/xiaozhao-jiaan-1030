"""Safety coverage pure regression: no DB, retrieval or LLM calls."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.qa_policy import DEFAULT_POLICY,RISK_RULES,screen_risk
from app.services.qa_graph import node_screen_risk
CASES = [
 ('阿公今天喘喘的','respiratory_abnormality'),
 ('阿嬤胸痛又喘','respiratory_abnormality'),
 ('長輩呼吸急促','respiratory_abnormality'),
 ('長輩異常嗜睡、叫不醒','consciousness_abnormality'),
 ('長輩很難叫醒，反應異常','consciousness_abnormality'),
 ('長輩跌倒了','fall_head_impact'),
 ('跌倒撞到頭','fall_head_impact'),
 ('長輩摔倒後頭部碰撞','fall_head_impact'),
 ('單側手腳無力，說話不清','sudden_neurologic_abnormality'),
 ('突然一邊手腳沒力，講話也變得不太清楚','sudden_neurologic_abnormality'),
 ('突然口齒不清','sudden_neurologic_abnormality'),
 ('咖啡色嘔吐物','abnormal_vomiting_or_intake'),
 ('長輩剛剛吐了，看起來有一點咖啡色的東西','abnormal_vomiting_or_intake'),
 ('異常嘔吐物','abnormal_vomiting_or_intake'),
 ('長輩幾乎沒喝水，嘴乾，精神差','abnormal_vomiting_or_intake'),
 ('喝水少，嘴乾，精神差','abnormal_vomiting_or_intake'),
 ('阿嬤今天幾乎都沒喝水，嘴巴很乾，整個人也比平常沒精神','abnormal_vomiting_or_intake'),
 ('飲水明顯減少，精神狀態改變','abnormal_vomiting_or_intake'),
 ('要買哪種感冒藥','medication_selection'),
 ('哪種感冒藥比較適合','medication_selection'),
 ('要買什麼藥','medication_selection'),
 ('幫他選藥','medication_selection'),
 ('藥局買哪種','medication_selection'),
 ('長輩感冒，家屬叫我去藥局買感冒藥，要買哪一種？','medication_selection'),
]
NEGATIVES=['可以幫忙買藥嗎','可以代領藥嗎','照服員可以幫忙買藥嗎','可以代購藥品嗎','居家喘息服務的申請條件是什麼','長輩今天喝水很少','長輩嘴巴很乾']
class SafetyCoverage(unittest.TestCase):
 def test_family_coverage(self):
  for question,expected in CASES:
   with self.subTest(question=question):
    codes=[r.code for r in screen_risk(question)];self.assertIn(expected,codes)
    if expected=='medication_selection' and '藥' in question:self.assertIn('medication',codes)
 def test_negative_controls(self):
  for q in NEGATIVES:
   with self.subTest(question=q):self.assertEqual(screen_risk(q),[])
 def test_existing_routes_and_priority(self):
  for q,expected in [('胸痛','emergency'),('是不是肺炎','clinical'),('買藥後吃幾顆','medication'),('補助多少','subsidy_amount')]:
   self.assertEqual(screen_risk(q)[0].code,expected)
  self.assertEqual(screen_risk('胸痛又喘')[0].code,'emergency')
 def test_existing_escalation_flow(self):
  for q,expected in CASES:
   result=node_screen_risk({'question_masked':q,'policy':DEFAULT_POLICY,'checks':{}})
   self.assertEqual(result['outcome'],'escalate');self.assertIn(expected,result['risk_codes'])
   self.assertEqual(result['reason'],'risk_'+result['risk_codes'][0])
 def test_version_and_thresholds_unchanged(self):
  self.assertEqual(DEFAULT_POLICY.version,'2026-10-12.systematic.1')
  expected={'top_k':5,'candidate_k':50,'lexical_weight':.55,'min_top_coverage':.18,'min_combined':.24,'min_evidence_score':.16,'min_support':.45,'min_gate_vector':.52,'min_gate_body_topic':.5,'min_gate_title_topic':.8,'min_gate_rule_topic':.8}
  for key,value in expected.items():self.assertEqual(getattr(DEFAULT_POLICY,key),value)
  for r in RISK_RULES[4:]:
   for forbidden in ['中風','肺炎','低血糖','消化道出血','脫水']:self.assertNotIn(forbidden,r.label)
if __name__=='__main__':
 for q,_ in CASES:print(q,'=>',','.join(r.code for r in screen_risk(q)))
 unittest.main(verbosity=2)
