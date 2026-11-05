import json
import unittest
from pathlib import Path
from app.services.mpc_submission_guard import MpcSubmissionBlocked, validated_ordinary_summary

DATA = Path(__file__).resolve().parents[1] / 'mpc_test_fixtures' / 'handover_payloads_for_backend.json'


class MPCSubmitGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads = {k: v['api_confirm_payload'] for k, v in json.loads(DATA.read_text(encoding='utf-8')).items()}

    def review(self, p, summary='家屬要求協助買藥，需居督確認是否符合服務範圍。'):
        return {'acknowledge_review': True, 'selected_idx': p['selected_idx'],
                'confirmed_summary': summary, 'role_corrections': {}}

    def test_ba16_review_accepted(self):
        p = self.payloads['CASE_01_BA16_MED']
        self.assertIn('居督', validated_ordinary_summary(p, self.review(p)))

    def test_harassment_review_accepted(self):
        p = self.payloads['CASE_02_BATH_HARASS_MULTI']
        self.assertTrue(validated_ordinary_summary(p, self.review(p)))

    def test_environment_hazard_review_accepted_for_case_with_manual_triage(self):
        p = self.payloads['CASE_03_OOD_MOUNTAIN_DOGS']
        self.assertTrue(validated_ordinary_summary(p, self.review(p, '案家附近犬隻與淹水阻路，暫停進入並請居督確認。')))

    def test_sos_rejected(self):
        p = self.payloads['CASE_04_P0_EMERGENCY_SOS']
        with self.assertRaises(MpcSubmissionBlocked):
            validated_ordinary_summary(p, self.review(p))

    def test_forged_safe_flag_still_blocked_on_urgent_words(self):
        p = json.loads(json.dumps(self.payloads['CASE_04_P0_EMERGENCY_SOS']))
        p['fsm_state'] = 'Waiting_LINE_Confirm'
        p['active_intents'] = ['Case_Report']
        p['slot_state']['service_domain'] = 'BA_22'
        for seg in p['segments']: seg['safety_flag'] = 'SAFE'
        with self.assertRaises(MpcSubmissionBlocked):
            validated_ordinary_summary(p, self.review(p))

    def test_technical_text_blocked(self):
        p = self.payloads['CASE_01_BA16_MED']
        with self.assertRaises(MpcSubmissionBlocked):
            validated_ordinary_summary(p, self.review(p, '跨輪解纏結重寫 FAMILY對CAREGIVER'))

    def test_no_ack_blocked(self):
        p = self.payloads['CASE_01_BA16_MED']; r = self.review(p); r['acknowledge_review'] = False
        with self.assertRaises(MpcSubmissionBlocked): validated_ordinary_summary(p, r)

    def test_unselected_segment_blocked(self):
        p = self.payloads['CASE_01_BA16_MED'];r=self.review(p);r['selected_idx']=[0,1]
        with self.assertRaises(MpcSubmissionBlocked): validated_ordinary_summary(p,r)

if __name__=='__main__': unittest.main()
