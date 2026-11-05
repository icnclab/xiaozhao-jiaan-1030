import json
import unittest
from pathlib import Path
from app.services.mpc_handover import build_preview, MpcPayloadError

DATA = Path(__file__).resolve().parents[1] / 'mpc_test_fixtures' / 'handover_payloads_for_backend.json'

class MpcHandoverUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = json.loads(DATA.read_text(encoding='utf-8'))

    def test_all_five_scenarios_build(self):
        for key, testcase in self.fixtures.items():
            with self.subTest(case=key):
                actual = build_preview(testcase['api_confirm_payload'])
                self.assertEqual(len(actual['selected_segments']), len(actual['selected_idx']))
                self.assertTrue(actual['requires_human_confirmation'])
                self.assertFalse(actual['saved'])
                self.assertFalse(actual['notification_sent'])

    def test_hazardous_ood_not_safe(self):
        v=build_preview(self.fixtures['CASE_03_OOD_MOUNTAIN_DOGS']['api_confirm_payload'])
        self.assertTrue(v['requires_safety_review'])

    def test_sos_not_auto_sent(self):
        v=build_preview(self.fixtures['CASE_04_P0_EMERGENCY_SOS']['api_confirm_payload'])
        self.assertTrue(v['emergency_candidate'])
        self.assertFalse(v['notification_sent'])

    def test_reject_invalid_selected_index(self):
        x=dict(self.fixtures['CASE_01_BA16_MED']['api_confirm_payload'])
        x['selected_idx']=[999]
        with self.assertRaises(MpcPayloadError): build_preview(x)

    def test_reject_inconsistent_emergency(self):
        x=dict(self.fixtures['CASE_04_P0_EMERGENCY_SOS']['api_confirm_payload'])
        x['fsm_state']='Waiting_LINE_Confirm'
        with self.assertRaises(MpcPayloadError): build_preview(x)

if __name__=='__main__': unittest.main()
