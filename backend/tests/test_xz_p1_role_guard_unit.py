import unittest
from app.services.jiaan1030_role_guard import make_role_aware


class RiskRoleTest(unittest.TestCase):
    def test_caregiver_possible_death(self):
        msg = make_role_aware('risk_emergency', 'caregiver', '請通知督導確認', question='個案疑似死亡沒有呼吸')
        self.assertIn('119', msg)
        self.assertIn('不能依描述判定死亡', msg)
        self.assertIn('不要自行宣布死亡', msg)

    def test_supervisor_confirmed_claim(self):
        msg = make_role_aware('risk_emergency', 'supervisor', '請通知督導確認', question='我的個案死亡，要怎麼處理')
        self.assertIn('無法核實', msg)
        self.assertIn('督導／主管', msg)
        self.assertNotIn('請通知督導確認', msg)

    def test_supervisor_other_risk(self):
        msg = make_role_aware('risk_medication', 'supervisor', '請通知督導確認', question='我要停藥')
        self.assertIn('居督', msg)
        self.assertNotIn('請通知督導確認', msg)

    def test_error_unchanged(self):
        msg = make_role_aware('llm_error', 'supervisor', '系統故障', question='我的個案死亡')
        self.assertEqual('系統故障', msg)


if __name__ == '__main__':
    unittest.main()
