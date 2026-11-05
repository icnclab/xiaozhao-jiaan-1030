import json
import unittest
from pathlib import Path
from app.services.mpc_handover import build_preview, build_review_draft, MpcPayloadError
DATA=Path(__file__).resolve().parents[1]/'mpc_test_fixtures'/'handover_payloads_for_backend.json'
class ReviewUnitTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.data=json.loads(DATA.read_text(encoding='utf-8'))
 def review(self,p):
  return {'acknowledge_review':True, 'selected_idx':p['selected_idx'], 'confirmed_summary':'【人工確認】測試摘要', 'role_corrections':{}}
 def test_all_five_previews(self):
  for name,d in self.data.items():
   with self.subTest(name=name):
    p=d['api_confirm_payload']; out=build_preview(p)
    self.assertFalse(out['saved']); self.assertFalse(out['notification_sent'])
 def test_all_five_review_drafts(self):
  for name,d in self.data.items():
   with self.subTest(name=name):
    p=d['api_confirm_payload']; out=build_review_draft(p,self.review(p))
    self.assertTrue(out['review_only']); self.assertFalse(out['case_created']); self.assertFalse(out['notification_sent'])
 def test_no_acknowledgement(self):
  p=self.data['CASE_01_BA16_MED']['api_confirm_payload'];r=self.review(p);r['acknowledge_review']=False
  with self.assertRaises(MpcPayloadError):build_review_draft(p,r)
 def test_cannot_add_segment(self):
  p=self.data['CASE_01_BA16_MED']['api_confirm_payload'];r=self.review(p);r['selected_idx']=[0,1]
  with self.assertRaises(MpcPayloadError):build_review_draft(p,r)
 def test_invalid_role(self):
  p=self.data['CASE_01_BA16_MED']['api_confirm_payload'];r=self.review(p);r['role_corrections']={'說話者一':'DIRECTOR_OF_WORLD'}
  with self.assertRaises(MpcPayloadError):build_review_draft(p,r)
 def test_ood_safe_flag_still_review(self):
  p=self.data['CASE_03_OOD_MOUNTAIN_DOGS']['api_confirm_payload']
  self.assertTrue(build_review_draft(p,self.review(p))['requires_supervisor_review'])
 def test_sos_cannot_auto_send(self):
  p=self.data['CASE_04_P0_EMERGENCY_SOS']['api_confirm_payload'];o=build_review_draft(p,self.review(p))
  self.assertTrue(o['emergency_candidate']);self.assertFalse(o['notification_sent'])
 def test_invalid_idx_and_state(self):
  p=dict(self.data['CASE_04_P0_EMERGENCY_SOS']['api_confirm_payload']);p['selected_idx']=[444]
  with self.assertRaises(MpcPayloadError):build_preview(p)
if __name__=='__main__': unittest.main()
