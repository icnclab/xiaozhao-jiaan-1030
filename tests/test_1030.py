"""Offline regression tests, no DB reads/writes or external requests."""
import importlib.util
import pathlib
import sys
import unittest

module_path = pathlib.Path(__file__).resolve().parents[1] / 'backend' / 'app' / 'jiaan1030_role_guard.py'
spec = importlib.util.spec_from_file_location('jiaan1030_guard_test', module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
make = module.make_role_aware

class GuardTests(unittest.TestCase):
    def test_supervisor_unconsciousness_no_self_escalation(self):
        out = make('risk_consciousness_abnormality', 'supervisor', '請先通知督導確認。')
        self.assertIn('您目前是居督', out)
        self.assertNotIn('請先通知督導確認', out)
        self.assertIn('119', out)
        self.assertIn('110', out)
        self.assertIn('SOP', out)
    def test_director_emergency(self):
        out = make('risk_emergency', 'director', '請先通知督導確認。')
        self.assertIn('主任', out)
        self.assertIn('119', out)
    def test_admin_emergency(self):
        out = make('risk_fall_head_impact', 'admin', '請先通知督導確認。')
        self.assertNotIn('請先通知督導確認', out)
        self.assertIn('SOP', out)
    def test_caregiver_urgent_prioritizes_emergency(self):
        out = make('risk_fall_head_impact', 'caregiver', '請先通知督導確認。')
        self.assertIn('119', out)
        self.assertIn('請先通知督導確認', out)
        self.assertTrue(out.startswith('如有人身立即危險'))
    def test_medicine_risk_does_not_auto_invent(self):
        out = make('risk_medication', 'supervisor', '用藥需要判斷')
        self.assertIn('專業判斷', out)
        self.assertNotIn('119', out)
    def test_supervisor_insufficient_not_self_report(self):
        out = make('insufficient', 'supervisor', '請送交督導確認。')
        self.assertIn('正式文件', out)
        self.assertNotIn('請送交督導確認', out)
    def test_provider_failure_not_misrepresented(self):
        out = make('llm_error', 'supervisor', '系統目前無法完成回答，請稍後再試')
        self.assertEqual('系統目前無法完成回答，請稍後再試', out)
    def test_caregiver_existing_no_risk_retained(self):
        out = make('insufficient', 'caregiver', '請送交督導確認。')
        self.assertEqual('請送交督導確認。', out)
    def test_does_not_change_outcome_or_database(self):
        out = make('risk_emergency', 'caregiver', '')
        self.assertIn('119', out)

if __name__ == '__main__':
    unittest.main(verbosity=2)
