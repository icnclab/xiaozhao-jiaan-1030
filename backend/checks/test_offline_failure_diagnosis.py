"""Synthetic offline attribution and additive report compatibility tests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from offline_failure_diagnosis import (diagnose, attach_diagnoses, existing_error_types,
                                      write_improvement_reports, STAGES, COLUMNS, VERSION)
from offline_rag_metrics import digest, stage


def fixture(stages=("evidence_gate",), status="confirmed"):
    snapshots = {key: stage([{ "chunk_id": "synthetic-a", "text": "????", "ref": "E1" }])
                 for key in {k for spec in STAGES.values() for k in spec["snapshots"]}}
    trace = {key: {"observation": "??????"}
             for key in {k for spec in STAGES.values() for k in spec["trace"]}}
    row = dict(id="synthetic-case", error_type="incomplete_answer", expected_behavior="answer",
               pass_result=False, outcome="answer", behavior="answer", offline_snapshots=snapshots,
               checks=trace, fail_reason=["missing:????"])
    annotation = dict(error_type="incomplete_answer", annotation_version="synthetic-diagnosis-1",
                      snapshot_sha256=digest(snapshots), trace_sha256=digest(trace),
                      human_review=dict(method="synthetic", review_id="review-synthetic-1", failure=True, status="approved"),
                      causes=[])
    for name in stages:
        evidence = []
        for kind, keys, root in (("snapshot", STAGES[name]["snapshots"], snapshots), ("trace", STAGES[name]["trace"], trace)):
            for key in keys:
                evidence.append(dict(kind=kind, path=[key], sha256=digest(root[key]), finding="?????????"))
        annotation["causes"].append(dict(failure_stage=name, failure_cause="synthetic_supported_cause",
                                           diagnosis_status=status, rationale="???????????????", evidence=evidence))
    return row, annotation


class FailureDiagnosisTests(unittest.TestCase):
    def test_same_error_different_stages(self):
        first, a = fixture(("evidence_gate",))
        second, b = fixture(("answer_presentation",))
        x, y = diagnose(first, a)[0], diagnose(second, b)[0]
        self.assertEqual(x["error_type"], y["error_type"])
        self.assertNotEqual(x["failure_stage"], y["failure_stage"])
        self.assertEqual(x["diagnosis_status"], "confirmed")
        self.assertEqual(y["diagnosis_status"], "confirmed")

    def test_multiple_candidate_causes_preserved(self):
        row, a = fixture(("evidence_gate", "evidence_selection"), "suspected")
        result = diagnose(row, a)
        self.assertEqual(len(result), 2)
        self.assertEqual({r["failure_stage"] for r in result}, {"evidence_gate", "evidence_selection"})
        self.assertTrue(all(r["diagnosis_status"] == "suspected" for r in result))

    def test_missing_trace_never_forces_attribution(self):
        row, a = fixture(); row["checks"] = {}
        d = diagnose(row, a)[0]
        self.assertEqual(d["diagnosis_status"], "undetermined")
        self.assertIsNone(d["failure_stage"])
        self.assertIsNone(d["trace_id"])

    def test_missing_snapshot_never_forces_attribution(self):
        row, a = fixture(); row["offline_snapshots"] = {}
        self.assertIsNone(diagnose(row, a)[0]["failure_cause"])

    def test_missing_annotation_never_forces_attribution(self):
        row, _ = fixture()
        self.assertEqual(diagnose(row)[0]["reason"], "diagnosis_annotation_missing")

    def test_missing_human_review_never_forces_attribution(self):
        row, a = fixture(); del a["human_review"]
        self.assertEqual(diagnose(row, a)[0]["reason"], "human_annotation_missing")

    def test_correct_safety_refusal_not_failure(self):
        row, a = fixture(("safety_routing",))
        row.update(expected_behavior="refuse", behavior="refuse", outcome="escalate", pass_result=True, reason="risk_medication")
        d = diagnose(row, a)[0]
        self.assertFalse(d["is_failure"])
        self.assertIsNone(d["error_type"])
        self.assertIsNone(d["failure_stage"])

    def test_correct_supervisor_escalation_not_failure(self):
        row, _ = fixture(); row.update(expected_behavior="escalate", behavior="escalate", pass_result=True, reason="no_evidence")
        self.assertFalse(diagnose(row)[0]["is_failure"])

    def test_correct_clarification_not_failure(self):
        row, _ = fixture(); row.update(expected_behavior="clarify", behavior="clarify", pass_result=True)
        self.assertFalse(diagnose(row)[0]["is_failure"])

    def test_reason_code_is_not_error_type(self):
        row, a = fixture(); a["error_type"] = "unsupported_claim"; row["reason"] = "unsupported_claim"
        d = diagnose(row, a)[0]
        self.assertIsNone(d["error_type"])
        self.assertEqual(d["reason"], "invalid_or_missing_error_type")

    def test_reason_code_never_auto_converted(self):
        row, a = fixture(); del a["error_type"]; del row["error_type"]; row["reason"] = "no_evidence"
        self.assertIsNone(diagnose(row, a)[0]["error_type"])

    def test_canonical_14_types_preserved_without_app_import(self):
        types = existing_error_types()
        self.assertEqual(len(types), 14)
        self.assertTrue({"wrong_answer", "retrieval_miss", "duplicate_citation", "verbose_answer"} <= types)
        self.assertFalse({"no_evidence", "unsupported_claim", "risk_medication"} & types)

    def test_no_reranker_stage(self):
        row, a = fixture(); a["causes"][0]["failure_stage"] = "reranker"
        d = diagnose(row, a)[0]
        self.assertEqual(d["diagnosis_status"], "undetermined")
        self.assertIsNone(d["failure_stage"])
        self.assertEqual(d["proposed_stage"], "reranker")

    def test_low_recall_not_embedding_or_topk_proof(self):
        for name in ("embedding", "top_k"):
            row, a = fixture((name,))
            row["offline_rag_metrics"] = {"candidate_context_recall": {"rate": 0}}
            a["causes"][0]["evidence"] = [{"kind": "metric", "path": ["candidate_context_recall"], "finding": "? recall"}]
            self.assertEqual(diagnose(row, a)[0]["diagnosis_status"], "undetermined")

    def test_low_faithfulness_not_generation_proof(self):
        row, a = fixture(("generation",))
        row["offline_rag_metrics"] = {"faithfulness": {"rate": 0}}
        a["causes"][0]["evidence"] = [{"kind": "metric", "path": ["faithfulness"], "finding": "? faithfulness"}]
        self.assertIsNone(diagnose(row, a)[0]["failure_stage"])

    def test_generation_requires_before_and_after_postprocessing(self):
        row, a = fixture(("generation",)); del row["offline_snapshots"]["post_generation_candidate_claims"]
        a["snapshot_sha256"] = digest(row["offline_snapshots"])
        self.assertEqual(diagnose(row, a)[0]["reason"], "stage_snapshot_missing")

    def test_embedding_missing_instrumentation_undetermined(self):
        row, a = fixture(("embedding",)); del row["checks"]["embedding_diagnostics"]
        a["trace_sha256"] = digest(row["checks"])
        self.assertEqual(diagnose(row, a)[0]["reason"], "stage_trace_missing")

    def test_observation_digest_mismatch(self):
        row, a = fixture(); a["trace_sha256"] = "stale"
        self.assertEqual(diagnose(row, a)[0]["reason"], "annotation_observation_mismatch")

    def test_invalid_evidence_hash_undetermined(self):
        row, a = fixture(); a["causes"][0]["evidence"][0]["sha256"] = "stale"
        self.assertEqual(diagnose(row, a)[0]["reason"], "invalid_or_unrelated_evidence")

    def test_confirmed_requires_approval(self):
        row, a = fixture(); a["human_review"]["status"] = "pending"
        self.assertEqual(diagnose(row, a)[0]["reason"], "confirmation_requires_approved_review")

    def test_reviewed_nonfailure_not_failure(self):
        row, a = fixture(); a["human_review"]["failure"] = False
        self.assertFalse(diagnose(row, a)[0]["is_failure"])

    def test_additive_old_report_compatibility(self):
        from run_answer_quality_v1 import evaluate, summarize
        case = dict(id="unit", question="??", category="synthetic", expected_behavior="answer", must_include=[],
                    must_not_include=[], expected_source_keywords=[], expected_risk_result="none",
                    expected_should_escalate=False, human_review_required=False)
        actual = dict(answer="??", source=[], behavior="answer", risk_result=[], escalation=False)
        row = dict(case, **actual, **evaluate(case, actual))
        original = copy.deepcopy(row); before = summarize([row])
        attach_diagnoses([row])
        self.assertEqual(summarize([row]), before)
        self.assertEqual({k: v for k, v in row.items() if k != "offline_failure_diagnoses"}, original)

    def test_gold_statistics_remain_unchanged(self):
        from checks.evaluate_gold_v1 import assess, statistics
        from test_gold_baseline import record, actual
        row = assess(record("answer"), actual("escalate"), {})
        original = copy.deepcopy(row)
        before = statistics([row])
        attach_diagnoses([row])
        self.assertEqual(statistics([row]), before)
        self.assertEqual({k: v for k, v in row.items() if k != "offline_failure_diagnoses"}, original)

    def test_pending_review_may_remain_suspected(self):
        row, a = fixture(status="suspected"); a["human_review"]["status"] = "pending"
        self.assertEqual(diagnose(row, a)[0]["diagnosis_status"], "suspected")
        self.assertTrue(diagnose(row, a)[0]["human_review"]["required"])

    def test_existing_bound_metrics_preserved_with_provenance(self):
        row, a = fixture()
        row["offline_rag_metrics"] = dict(snapshot_sha256=digest(row["offline_snapshots"]),
                                          evaluator_version="offline-rag-1.0", annotation_version="synthetic-metric-1",
                                          candidate_context_recall=dict(numerator=0, denominator=1, rate=0, reason=None))
        d = diagnose(row, a)[0]
        self.assertEqual(d["before_metrics"]["status"], "measured")
        self.assertEqual(d["before_metrics"]["values"]["candidate_context_recall"]["rate"], 0)
        self.assertEqual(d["after_metrics"]["status"], "not_tested")

    def test_research_diagnosis_is_separate_from_runner(self):
        import contextlib
        import io
        import sys
        from unittest.mock import patch
        import run_answer_quality_v1 as runner
        row, a = fixture()
        case = dict(id=row["id"], question="????", category="synthetic", expected_behavior="answer",
                    must_include=["??????????"], must_not_include=[], expected_source_keywords=[],
                    expected_risk_result="none", expected_should_escalate=False, human_review_required=False)
        row.update(case, answer="????", source=[], risk_result=[], escalation=False)
        row["offline_failure_diagnoses"] = [{"synthetic_research_only": True}]
        with tempfile.TemporaryDirectory(prefix="offline_diagnosis_cli_") as folder:
            root = Path(folder)
            (root/"dataset.json").write_text(json.dumps({"cases": [case]}), encoding="utf-8")
            (root/"saved.json").write_text(json.dumps({"metadata": {"dataset_sha256": "synthetic"}, "results": [row]}), encoding="utf-8")
            (root/"diagnoses.json").write_text(json.dumps({"schema_version": 1, "cases": {row["id"]: a}}), encoding="utf-8")
            args = ["runner", "--dataset", str(root/"dataset.json"), "--reevaluate", str(root/"saved.json"),
                    "--output", str(root/"report")]
            with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(), 1)
            report = json.loads((root/"report/results.json").read_text(encoding="utf-8"))
            self.assertEqual(report["statistics"]["overall_pass_rate"]["denominator"], 1)
            self.assertFalse(report["results"][0]["pass_result"])
            self.assertNotIn("offline_failure_diagnoses", report["results"][0])
            self.assertFalse((root/"report/failure_cases.csv").exists())
            self.assertFalse((root/"report/failure_cases.md").exists())
            # Research use is explicit and separated from ordinary reports.
            attach_diagnoses(report["results"], {row["id"]: a})
            research = root/"research"
            research.mkdir()
            write_improvement_reports(research, report["results"])
            self.assertEqual(report["results"][0]["offline_failure_diagnoses"][0]["diagnosis_status"], "confirmed")
            self.assertTrue((research/"failure_cases.csv").exists())
            self.assertTrue((research/"failure_cases.md").exists())

    def test_unmeasured_before_after_and_requested_columns(self):
        row, a = fixture(); attach_diagnoses([row], {row["id"]: a})
        with tempfile.TemporaryDirectory(prefix="offline_failure_unit_") as folder:
            write_improvement_reports(folder, [row])
            report = json.loads((Path(folder)/"failure_cases.json").read_text(encoding="utf-8"))
            record = report["results"][0]
            self.assertEqual(record["before_metrics"]["status"], "not_tested")
            self.assertEqual(record["after_metrics"]["status"], "not_tested")
            self.assertEqual(record["change"]["status"], "not_changed")
            header = (Path(folder)/"failure_cases.csv").read_text(encoding="utf-8-sig").splitlines()[0]
            self.assertEqual(header.split(",")[:len(COLUMNS)], COLUMNS)
            self.assertIn("??", (Path(folder)/"failure_cases.md").read_text(encoding="utf-8"))
            self.assertEqual(record["evaluator_version"], VERSION)
            self.assertTrue(record["evidence"])
            self.assertTrue(record["snapshot_id"])
            self.assertTrue(record["trace_id"])
            self.assertTrue(record["human_review"]["review_id"])
            with self.assertRaises(FileExistsError): write_improvement_reports(folder, [row])

    def test_mixed_causes_do_not_force_single_diagnosis(self):
        row, a = fixture(("evidence_gate", "generation"))
        a["causes"][1]["evidence"] = []
        results = diagnose(row, a)
        self.assertEqual([r["diagnosis_status"] for r in results], ["confirmed", "undetermined"])

    def test_after_never_filled_from_before_or_change(self):
        row, a = fixture(); a["change"] = {"status": "proposed", "description": "?????"}
        a["after_metrics"] = {"faithfulness": 1}
        d = diagnose(row, a)[0]
        self.assertEqual(d["after_metrics"]["status"], "not_tested")
        self.assertIsNone(d["after_metrics"]["values"])

    def test_unbound_metrics_not_credited_as_measurement(self):
        row, a = fixture(); row["offline_rag_metrics"] = {"snapshot_sha256": "wrong", "evaluator_version": "fake", "faithfulness": {"rate": 1}}
        self.assertEqual(diagnose(row, a)[0]["before_metrics"]["status"], "not_tested")


if __name__ == "__main__":
    unittest.main(verbosity=2)
