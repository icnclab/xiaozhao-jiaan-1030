import unittest
from unittest.mock import MagicMock
from app.api.jiaan1030_service_catalog import _catalog

class CatalogGateTests(unittest.TestCase):
    def test_public_requires_double_approval(self):
        db = MagicMock()
        db.execute.return_value.mappings.return_value.all.return_value = []
        _catalog(db, True)
        calls = [str(x.args[0]) for x in db.execute.call_args_list]
        self.assertIn("reviewed = TRUE", calls[0])
        self.assertIn("reviewed = TRUE", calls[1])
        self.assertIn("schema_status = 'approved'", calls[1])
        self.assertNotIn("schema_status", calls[0])

    def test_review_keeps_unapproved_visible_to_reviewers(self):
        db = MagicMock()
        db.execute.return_value.mappings.return_value.all.return_value = []
        _catalog(db, False)
        calls = [str(x.args[0]) for x in db.execute.call_args_list]
        self.assertEqual(len(calls), 2)
        self.assertNotIn("WHERE reviewed", calls[1])
        self.assertNotIn("schema_status = 'approved'", calls[1])

if __name__ == "__main__":
    unittest.main(verbosity=2)
