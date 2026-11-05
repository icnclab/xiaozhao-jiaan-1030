import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import jiaan1030_official_source as source

VERSION = "test-version-001"
GOOD_URL = "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=D0050051"


class OfficialSourceTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.approvals = Path(self.temp.name) / "approved.json"
        self.patcher = patch.object(source, "_APPROVALS", self.approvals)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def approve(self, url=GOOD_URL, reviewed=True, reviewer="tester"):
        self.approvals.write_text(
            json.dumps({
                VERSION: {
                    "url": url,
                    "reviewed": reviewed,
                    "reviewer": reviewer
                }
            }),
            encoding="utf-8"
        )

    def check(self, url=GOOD_URL):
        return source.get_reviewed_official_source(
            VERSION, url, "測試法規"
        )

    def test_01_no_approval_file(self):
        self.assertIsNone(self.check())

    def test_02_unreviewed_rejected(self):
        self.approve(reviewed=False)
        self.assertIsNone(self.check())

    def test_03_missing_reviewer_rejected(self):
        self.approve(reviewer="")
        self.assertIsNone(self.check())

    def test_04_version_mismatch_rejected(self):
        self.approve()
        self.assertIsNone(
            source.get_reviewed_official_source(
                "another-version", GOOD_URL, "測試法規"
            )
        )

    def test_05_url_mismatch_rejected(self):
        self.approve()
        self.assertIsNone(
            self.check("https://www.mohw.gov.tw/")
        )

    def test_06_http_rejected(self):
        url = GOOD_URL.replace("https:", "http:")
        self.approve(url=url)
        self.assertIsNone(self.check(url))

    def test_07_fake_government_domain_rejected(self):
        url = "https://law.moj.gov.tw.evil.example/path"
        self.approve(url=url)
        self.assertIsNone(self.check(url))

    def test_08_redirect_parameter_rejected(self):
        url = GOOD_URL + "&redirect=https://evil.example"
        self.approve(url=url)
        self.assertIsNone(self.check(url))

    def test_09_embedded_credentials_rejected(self):
        url = "https://user:pass@law.moj.gov.tw/path"
        self.approve(url=url)
        self.assertIsNone(self.check(url))

    def test_10_valid_approved_source_accepted(self):
        self.approve()
        result = self.check()
        self.assertIsNotNone(result)
        self.assertTrue(result["verified"])
        self.assertEqual(result["official_url"], GOOD_URL)
        self.assertEqual(result["title"], "測試法規")


if __name__ == "__main__":
    unittest.main(verbosity=2)
