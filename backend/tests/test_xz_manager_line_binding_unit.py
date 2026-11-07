"""P0 manager LINE binding policy, no database or external calls."""
import unittest
from app.services.jiaan_line_binding_policy import can_issue_binding_code, requires_verified_real_line


class TestManagerLineBindingPolicy(unittest.TestCase):
    def test_existing_caregiver_issuance(self):
        for actor in ('supervisor','director','admin'):
            self.assertTrue(can_issue_binding_code(actor,'actor','caregiver','caregiver'))

    def test_supervisor_can_only_issue_self_manager(self):
        self.assertTrue(can_issue_binding_code('supervisor','s1','supervisor','s1'))
        self.assertFalse(can_issue_binding_code('supervisor','s1','supervisor','s2'))
        self.assertFalse(can_issue_binding_code('supervisor','s1','director','d1'))
        self.assertFalse(can_issue_binding_code('supervisor','s1','admin','a1'))

    def test_director_can_issue_supervisor_and_self(self):
        self.assertTrue(can_issue_binding_code('director','d1','supervisor','s1'))
        self.assertTrue(can_issue_binding_code('director','d1','director','d1'))
        self.assertFalse(can_issue_binding_code('director','d1','director','d2'))
        self.assertFalse(can_issue_binding_code('director','d1','admin','a1'))

    def test_admin_and_unknown_role(self):
        for target in ('caregiver','supervisor','director','admin'):
            self.assertTrue(can_issue_binding_code('admin','a1',target,'any'))
        self.assertFalse(can_issue_binding_code('admin','a1','unexpected','any'))
        self.assertFalse(can_issue_binding_code('caregiver','c1','caregiver','c1'))

    def test_manager_requires_real_line(self):
        self.assertFalse(requires_verified_real_line('caregiver'))
        for role in ('supervisor','director','admin'):
            self.assertTrue(requires_verified_real_line(role))


if __name__ == '__main__':
    unittest.main()
