"""Direct unittest; no pytest fixtures, DB, app imports or network."""
import copy
import json
import socket
import unittest
from unittest.mock import patch
from audit_official_recall_review import ba16_points, norm, eligible, short_form, OUT, ROOT, sha, VERIFIED


class OfficialReviewTests(unittest.TestCase):
    def test_whitespace_only_normalization(self):
        self.assertEqual(norm("五 公里\n50%"), "五公里50%")
        self.assertNotEqual(norm("五公里"), norm("十公里"))

    def test_ba15_prefix_excluded(self):
        text = "BA15不得引用。一、目的物品或事項包括：甲。二、乙。三、丙。四、丁。超過五公里所需費用由長照給付對象自行負擔。BA17a不得引用。"
        points = ba16_points(text)
        self.assertEqual(len(points), 4)
        self.assertNotIn("BA15", "".join(points))
        self.assertNotIn("BA17a", "".join(points))

    def test_incomplete_ba16_fails_closed(self):
        with self.assertRaises(ValueError):
            ba16_points("一、目的物品或事項包括：不完整")

    def test_official_verified_is_not_human_approved(self):
        self.assertFalse(eligible({"evidence_status": VERIFIED}))

    def test_signature_without_service_date_not_eligible(self):
        self.assertFalse(eligible({"human_approved": True, "reviewer": "synthetic", "signed_at": "synthetic"}))

    def test_no_need_review_not_eligible(self):
        c = {"human_approved": True, "reviewer": "synthetic", "signed_at": "synthetic",
             "service_date": "synthetic", "local_applicability_confirmed": True}
        self.assertFalse(eligible(c))

    def test_no_local_applicability_not_eligible(self):
        c = {"human_approved": True, "reviewer": "synthetic", "signed_at": "synthetic",
             "service_date": "synthetic", "necessity_review_complete": True}
        self.assertFalse(eligible(c))

    def test_generated_packet_has_no_approval(self):
        p = json.loads((OUT/"official_review_packet.json").read_text(encoding="utf-8"))
        self.assertEqual(len(p["cases"]), 6)
        self.assertTrue(all(not eligible(c) and c["reviewer"] is None for c in p["cases"]))
        self.assertTrue(all(f["human_approved"] is False for c in p["cases"] for f in c["draft_necessary_facts"]))

    def test_four_points_match_but_full_annex_differs(self):
        p = json.loads((OUT/"comparisons.json").read_text(encoding="utf-8"))
        self.assertEqual(p["ba16_point_matches"], [True]*4)
        self.assertFalse(p["whole_annex_sha256_equal"])
        self.assertEqual(p["official_ba16_pages"], [14,15])

    def test_preserved_inputs_unchanged(self):
        p = json.loads((OUT/"validation.json").read_text(encoding="utf-8"))
        self.assertEqual(p["protected_files_before"], p["protected_files_after"])
        self.assertTrue(all(sha(ROOT/name) == value for name,value in p["protected_files_before"].items()))

    def test_manual_is_guidance_without_legal_effective_date(self):
        p = json.loads((OUT/"official_review_packet.json").read_text(encoding="utf-8"))
        e = p["official_evidence"]["E05"]
        self.assertIn("指引", e["kind"])
        self.assertIsNone(e["formal_effective_date"])

    def test_missing_original_not_claimed_downloaded(self):
        p = json.loads((OUT/"official_review_packet.json").read_text(encoding="utf-8"))
        self.assertEqual(p["new_notice_caution"]["original_pdf_download_status"], "unavailable")

    def test_no_recall_numbers(self):
        p = json.loads((OUT/"official_review_packet.json").read_text(encoding="utf-8"))
        self.assertIsNone(p["recall_rates"])
        self.assertEqual(p["formal_recall_eligible"], 0)

    def test_short_form_keeps_original_questions(self):
        p = json.loads((OUT/"official_review_packet.json").read_text(encoding="utf-8"))
        text = short_form(p)
        self.assertTrue(all(c["question"] in text for c in p["cases"]))

    def test_signoff_boxes_start_unchecked(self):
        p = json.loads((OUT/"official_review_packet.json").read_text(encoding="utf-8"))
        text = short_form(p)
        self.assertNotIn("☑", text)
        self.assertEqual(text.count("□核准標註"), 6)


if __name__ == "__main__":
    def denied(*args, **kwargs):
        raise RuntimeError("Network forbidden in evidence-review tests")
    with patch.object(socket.socket, "connect", denied), patch.object(socket, "create_connection", denied):
        unittest.main(verbosity=2)
