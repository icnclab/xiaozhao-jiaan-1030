"""Synthetic only. No app imports, DB, settings, datasets or historical QA."""
import copy
import unittest
from offline_rag_metrics import evaluate, digest, stage, snapshots


def fixture():
    evidence = [{"chunk_id": "a", "ref": "E1", "text": "????????????", "applicable": True},
                {"chunk_id": "b", "ref": "E2", "text": "???????", "applicable": True}]
    snapshot = {"candidate_evidence": stage(evidence), "generation_context": stage(evidence),
                "display_claims": stage([{"text": "?????????????????", "refs": ["E1", "E2"]}]),
                "cited_sources": stage(evidence)}
    yes = {"supported": True, "source_ids": ["a", "b"]}
    annotation = {"annotation_version": "synthetic-1", "method": "synthetic",
                  "claim_decomposition_complete": True,
                  "required_facts": [{"id": "f1", "text": "???????", "candidate": yes, "selected": yes}],
                  "atomic_claims": [{"id": "c1", "text": "?????", "kind": "kb_fact", "display_claim_index": 0,
                                     "context": yes, "citation": yes}]}
    return copy.deepcopy(snapshot), copy.deepcopy(annotation)


def score(s, a, outcome="answer"):
    a["snapshot_sha256"] = digest(s)
    return evaluate(s, a, outcome)


class OfflineMetricsTests(unittest.TestCase):
    def test_missing_annotation(self):
        self.assertEqual(evaluate({})["faithfulness"]["reason"], "annotation_missing")

    def test_snapshot_mismatch(self):
        s, a = fixture(); a["snapshot_sha256"] = "stale"
        self.assertIsNone(evaluate(s, a)["faithfulness"]["rate"])

    def test_zero_facts_and_claims(self):
        s, a = fixture(); a["required_facts"] = []; a["atomic_claims"] = []; s["display_claims"] = stage([])
        r = score(s, a)
        self.assertEqual(r["candidate_context_recall"]["reason"], "zero_denominator")
        self.assertIsNone(r["faithfulness"]["rate"])

    def test_missing_snapshots(self):
        s, a = fixture(); s["generation_context"] = stage(reason="not_observed")
        r = score(s, a)
        self.assertIsNone(r["selected_context_recall"]["rate"])
        self.assertIsNone(r["faithfulness"]["rate"])
        self.assertEqual(r["candidate_context_recall"]["rate"], 1)

    def test_missing_fact_and_claim_annotations(self):
        s, a = fixture(); del a["required_facts"]; del a["atomic_claims"]
        r = score(s, a)
        self.assertIsNone(r["candidate_context_recall"]["rate"])
        self.assertIsNone(r["faithfulness"]["rate"])

    def test_non_kb_claims_separate(self):
        for kind in ("safety_notice", "policy_declaration"):
            s, a = fixture(); a["atomic_claims"][0]["kind"] = kind
            r = score(s, a)
            self.assertIsNone(r["faithfulness"]["rate"])
            self.assertEqual(r["excluded_claims"][0]["kind"], kind)

    def test_refusal_and_clarification(self):
        for outcome in ("escalate", "clarify"):
            s, a = fixture()
            self.assertEqual(score(s, a, outcome)["faithfulness"]["reason"], "not_applicable:" + outcome)

    def test_unannotated_claim_not_ignored(self):
        s, a = fixture(); s["display_claims"]["items"].append({"text": "????", "refs": []})
        self.assertIsNone(score(s, a)["faithfulness"]["rate"])

    def test_incomplete_decomposition(self):
        s, a = fixture(); a["claim_decomposition_complete"] = False
        self.assertIsNone(score(s, a)["faithfulness"]["rate"])

    def test_invalid_support_source(self):
        s, a = fixture(); a["required_facts"][0]["candidate"]["source_ids"] = ["absent"]
        self.assertIsNone(score(s, a)["candidate_context_recall"]["rate"])

    def test_supported_inapplicable_version_not_credited(self):
        s, a = fixture(); s["candidate_evidence"]["items"][0]["applicable"] = False
        self.assertIsNone(score(s, a)["candidate_context_recall"]["rate"])

    def test_citation_must_be_actual(self):
        s, a = fixture(); s["display_claims"]["items"][0]["refs"] = ["E1"]
        self.assertIsNone(score(s, a)["citation_support"]["rate"])

    def test_missing_judgement_not_full_score(self):
        s, a = fixture(); del a["atomic_claims"][0]["context"]
        self.assertIsNone(score(s, a)["faithfulness"]["rate"])

    def test_dataclass_lists_keep_structured_evidence(self):
        from dataclasses import dataclass
        from offline_rag_metrics import serialize
        @dataclass
        class Chunk:
            chunk_id: str
            text: str
        rows = [Chunk("a", "????")]
        s = snapshots({"retrieved": rows, "checks": {"retrieval_gate": {"admitted_chunk_ids": ["a"]}},
                       "offline_provider_input": rows})
        self.assertEqual(s["candidate_evidence"]["items"][0]["text"], "????")
        self.assertEqual(s["gate_evidence"]["items"][0]["chunk_id"], "a")
        self.assertEqual(s["generation_context"]["items"], serialize(rows))

    def test_stage_provenance_does_not_fabricate(self):
        s = snapshots({"retrieved": [], "evidence": [], "checks": {"retrieval_gate": {"admitted_chunk_ids": []}}})
        self.assertEqual(s["gate_evidence"]["items"], [])
        self.assertIsNone(s["generation_context"]["items"])
        self.assertIsNone(s["generation_candidate_claims"]["items"])

    def test_synthetic_reevaluation_report_preserves_exit_code(self):
        import contextlib
        import io
        import json
        import sys
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import run_answer_quality_v1 as runner
        s, a = fixture(); a["snapshot_sha256"] = digest(s)
        case = dict(id="synthetic", question="????", category="synthetic", expected_behavior="answer",
                    must_include=[], must_not_include=[], expected_source_keywords=[], expected_risk_result="none",
                    expected_should_escalate=False, human_review_required=False)
        actual = dict(answer="????", behavior="answer", outcome="answer", source=[], risk_result=[],
                      escalation=False, offline_snapshots=s)
        with tempfile.TemporaryDirectory(prefix="offline_metric_unit_") as folder:
            root = Path(folder)
            (root/"cases.json").write_text(json.dumps({"cases": [case]}), encoding="utf-8")
            (root/"saved.json").write_text(json.dumps({"metadata": {"dataset_sha256": "synthetic"},
                                                     "results": [dict(case, **actual)]}), encoding="utf-8")
            (root/"annotations.json").write_text(json.dumps({"schema_version": 1, "cases": {"synthetic": a}}), encoding="utf-8")
            args = ["runner", "--dataset", str(root/"cases.json"), "--reevaluate", str(root/"saved.json"),
                    "--annotations", str(root/"annotations.json"), "--output", str(root/"report")]
            with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(), 0)
            report = json.loads((root/"report/results.json").read_text(encoding="utf-8"))
            self.assertEqual(report["statistics"]["overall_pass_rate"]["denominator"], 1)
            self.assertEqual(report["results"][0]["offline_rag_metrics"]["faithfulness"]["rate"], 1)
            self.assertIn("offline_rag_metrics", (root/"report/results.csv").read_text(encoding="utf-8-sig"))
            self.assertEqual(report["metadata"]["offline_evaluator_version"], "offline-rag-1.1")
            # Unsupported annotations must not change the original successful exit.
            a["atomic_claims"][0]["context"] = {"supported": False, "source_ids": [], "errors": ["negation_flip"]}
            (root/"annotations.json").write_text(json.dumps({"schema_version": 1, "cases": {"synthetic": a}}), encoding="utf-8")
            args[-1] = str(root/"second")
            with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(), 0)
            second = json.loads((root/"second/results.json").read_text(encoding="utf-8"))
            self.assertEqual(second["results"][0]["offline_rag_metrics"]["faithfulness"]["rate"], 0)
            self.assertEqual(second["statistics"], report["statistics"])

    def test_provider_observer_no_behavior_change(self):
        import sys
        import types
        from unittest.mock import patch
        from offline_rag_metrics import run_graph_with_capture
        evidence = [{"chunk_id": "a", "text": "????"}]
        candidate = types.SimpleNamespace(claims=[{"text": "????"}])
        provider = types.SimpleNamespace(answer=lambda q, e: candidate)
        graph = types.ModuleType("qa_graph")
        original = lambda: provider
        graph.get_llm_provider = original
        graph.run_graph = lambda initial: {"candidate": graph.get_llm_provider().answer("????", evidence)}
        services = types.ModuleType("app.services"); services.qa_graph = graph
        app = types.ModuleType("app"); app.services = services
        with patch.dict(sys.modules, {"app": app, "app.services": services}):
            state = run_graph_with_capture({})
        self.assertIs(state["candidate"], candidate)
        self.assertEqual(state["offline_provider_input"], evidence)
        self.assertIs(graph.get_llm_provider, original)


def recall_case(kind):
    def test(self):
        s, a = fixture()
        if kind in ("complete", "paraphrase", "multi_evidence"):
            if kind == "paraphrase": a["required_facts"][0]["text"] = "?????????????"
            r = score(s, a)
            self.assertEqual(r["candidate_context_recall"]["rate"], 1)
            self.assertEqual(r["selected_context_recall"]["rate"], 1)
        else:
            no = {"supported": False, "source_ids": [], "errors": [kind]}
            a["required_facts"][0]["selected"] = no
            if kind != "candidate_only": a["required_facts"][0]["candidate"] = no
            if kind == "candidate_only": s["generation_context"] = stage([])
            if kind == "title_only": s["candidate_evidence"] = stage([{"chunk_id": "a", "title": "????", "text": "???"}])
            if kind == "inapplicable_version": s["candidate_evidence"]["items"][0]["applicable"] = False
            r = score(s, a)
            self.assertEqual(r["selected_context_recall"]["rate"], 0)
            self.assertEqual(r["candidate_context_recall"]["rate"], 1 if kind == "candidate_only" else 0)
    return test


for kind in ("complete", "paraphrase", "multi_evidence", "title_only", "missing_exception", "candidate_only", "inapplicable_version"):
    setattr(OfflineMetricsTests, "test_recall_" + kind, recall_case(kind))


def faith_case(kind):
    texts = {"negation_flip": "????????????", "number_error": "?????",
             "deadline_error": "???????", "role_swap": "?????????",
             "condition_omitted": "????????????", "restriction_omitted": "????????"}
    def test(self):
        s, a = fixture()
        if kind in ("verbatim", "paraphrase", "multi_evidence"):
            if kind == "paraphrase": s["display_claims"]["items"][0]["text"] = "???????????????"
            r = score(s, a); self.assertEqual(r["faithfulness"]["rate"], 1); self.assertEqual(r["citation_support"]["rate"], 1)
        elif kind == "fictional_reference":
            s["display_claims"]["items"][0]["refs"] = ["E999"]
            r = score(s, a); self.assertEqual(r["faithfulness"]["rate"], 1); self.assertEqual(r["citation_support"]["rate"], 0)
        else:
            s["display_claims"]["items"][0]["text"] = texts[kind]
            a["atomic_claims"][0]["text"] = texts[kind]
            for key in ("context", "citation"):
                a["atomic_claims"][0][key] = {"supported": False, "source_ids": ["a", "b"], "errors": [kind]}
            r = score(s, a); self.assertEqual(r["faithfulness"]["rate"], 0); self.assertEqual(r["citation_support"]["rate"], 0)
            self.assertEqual(r["faithfulness"]["details"][0]["errors"], [kind])
    return test


for kind in ("verbatim", "paraphrase", "multi_evidence", "negation_flip", "number_error", "deadline_error", "role_swap", "condition_omitted", "restriction_omitted", "fictional_reference"):
    setattr(OfflineMetricsTests, "test_faith_" + kind, faith_case(kind))

if __name__ == "__main__":
    unittest.main(verbosity=2)
