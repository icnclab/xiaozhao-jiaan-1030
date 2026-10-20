"""Synthetic-only tests. No real cases, app imports, DB or providers."""
import copy
import unittest
from offline_rag_metrics import digest, evaluate, snapshots, stage
from recall_baseline import report, score_case, losses, METRICS, historical_snapshot


def fixture():
    rows = [{"chunk_id": "synthetic-a", "text": "synthetic fact", "applicable": True}]
    s = {"candidate_evidence": stage(rows), "gate_evidence": stage(rows), "selected_evidence": stage(rows),
         "retrieval_execution": stage(True), "generation_context": stage(reason="model_not_called")}
    fact = {"id": "f1", "text": "synthetic fact", "references": [
        {"document": "synthetic document", "version": "synthetic-v1", "locator": "synthetic section"}]}
    case = {"id": "synthetic", "question": "synthetic question", "review_status": "approved",
            "reviewer": "synthetic-reviewer", "reviewed_at": "synthetic-date", "applicability": "home_care_confirmed",
            "required_facts": [fact]}
    yes = {"supported": True, "source_ids": ["synthetic-a"]}
    annotation = {"annotation_version": "synthetic-v1", "method": "human_review", "case_sha256": digest(case),
                  "snapshot_sha256": digest(s), "required_facts": [dict(fact, candidate=yes, gate=yes, selected=yes)]}
    obs = {"snapshot": s, "question": case["question"], "execution": "search_executed"}
    return case, obs, annotation


class RecallBaselineTests(unittest.TestCase):
    def test_three_stages_without_model_call(self):
        c, o, a = fixture(); r = score_case(c, o, a)
        self.assertEqual([r[k]["rate"] for k in METRICS], [1, 1, 1])
        self.assertIsNone(o["snapshot"]["generation_context"]["items"])

    def test_pending_review_not_scored(self):
        c, o, a = fixture(); c["review_status"] = "pending"
        self.assertTrue(all(score_case(c, o, a)[k]["rate"] is None for k in METRICS))

    def test_gate_loss(self):
        c, o, a = fixture()
        for key in ("gate", "selected"):
            a["required_facts"][0][key] = {"supported": False, "source_ids": []}
        r = score_case(c, o, a)
        self.assertEqual([r[k]["rate"] for k in METRICS], [1, 0, 0])
        self.assertEqual(losses(r)["facts"][0]["observation"], "gate_excluded_fact")

    def test_selection_loss(self):
        c, o, a = fixture(); a["required_facts"][0]["selected"] = {"supported": False, "source_ids": []}
        self.assertEqual(losses(score_case(c, o, a))["facts"][0]["observation"], "selection_omitted_fact")

    def test_search_loss(self):
        c, o, a = fixture()
        for key in ("candidate", "gate", "selected"):
            a["required_facts"][0][key] = {"supported": False, "source_ids": []}
        self.assertEqual(losses(score_case(c, o, a))["facts"][0]["observation"], "search_did_not_cover_fact")

    def test_snapshot_mismatch(self):
        c, o, a = fixture(); o["snapshot"]["candidate_evidence"]["reason"] = "changed"
        self.assertIsNone(score_case(c, o, a)[METRICS[0]]["rate"])

    def test_case_mismatch(self):
        c, o, a = fixture(); c["question"] += " changed"; o["question"] = c["question"]
        self.assertEqual(score_case(c, o, a)[METRICS[0]]["reason"], "annotation_case_mismatch")

    def test_question_mismatch(self):
        c, o, a = fixture(); o["question"] += " changed"
        self.assertEqual(score_case(c, o, a)[METRICS[0]]["reason"], "observation_question_mismatch")

    def test_no_search_never_zero_recall(self):
        c, o, a = fixture(); o["snapshot"]["retrieval_execution"] = stage(False)
        self.assertIsNone(score_case(c, o, a)[METRICS[0]]["rate"])

    def test_missing_gate_stage(self):
        c, o, a = fixture(); del o["snapshot"]["gate_evidence"]; a["snapshot_sha256"] = digest(o["snapshot"])
        r = score_case(c, o, a)
        self.assertIsNone(r["gate_context_recall"]["rate"])
        self.assertEqual(r["candidate_context_recall"]["rate"], 1)

    def test_missing_gate_judgement(self):
        c, o, a = fixture(); del a["required_facts"][0]["gate"]
        self.assertIsNone(score_case(c, o, a)["gate_context_recall"]["rate"])

    def test_no_facts(self):
        c, o, a = fixture(); c["required_facts"] = []
        self.assertEqual(score_case(c, o, a)[METRICS[0]]["reason"], "required_facts_not_annotated")

    def test_inapplicable_version_or_facility(self):
        c, o, a = fixture(); c["applicability"] = "institutional_only"
        self.assertIsNone(score_case(c, o, a)[METRICS[0]]["rate"])

    def test_missing_source_locator(self):
        c, o, a = fixture(); c["required_facts"][0]["references"][0]["locator"] = None
        self.assertIsNone(score_case(c, o, a)[METRICS[0]]["rate"])

    def test_fact_set_mismatch(self):
        c, o, a = fixture(); a["required_facts"][0]["text"] = "different fact"
        self.assertIsNone(score_case(c, o, a)[METRICS[0]]["rate"])

    def test_synthetic_annotations_not_formal(self):
        c, o, a = fixture(); a["method"] = "synthetic"
        self.assertIsNone(score_case(c, o, a)[METRICS[0]]["rate"])

    def test_historical_ids_not_model_input(self):
        s, status = historical_snapshot({"retrieval_result": [{"chunk_id": "a", "text": "synthetic"}],
                                        "evidence_refs": {"E1": "a"}})
        self.assertEqual(status, "search_executed")
        self.assertIsNone(s["selected_evidence"]["items"])
        self.assertIsNone(s["generation_context"]["items"])

    def test_historical_safety_block(self):
        s, status = historical_snapshot({"checks": {"risk_codes": ["synthetic"]}, "retrieval_result": []})
        self.assertEqual(status, "safety_blocked_without_search")
        self.assertIs(s["retrieval_execution"]["items"], False)

    def test_gate_ids_incomplete(self):
        s = snapshots({"retrieved": [], "checks": {"retrieval_gate": {"admitted_chunk_ids": ["a"]}}})
        self.assertIsNone(s["gate_evidence"]["items"])

    def test_selected_different_from_provider(self):
        c, o, a = fixture(); o["snapshot"]["generation_context"] = stage([])
        a["snapshot_sha256"] = digest(o["snapshot"])
        self.assertEqual(score_case(c, o, a)["selected_context_recall"]["rate"], 1)

    def test_common_cohort_prevents_mixed_denominators(self):
        c, o, a = fixture(); del a["required_facts"][0]["gate"]
        r = report({"cases": [c]}, {"cases": {c["id"]: o}}, {c["id"]: a})
        self.assertEqual(r["common_measurable_case_count"], 0)
        self.assertTrue(all(r["statistics"][k]["rate"] is None for k in METRICS))

    def test_report_repeatable(self):
        c, o, a = fixture(); args = ({"cases": [c]}, {"cases": {c["id"]: o}}, {c["id"]: a})
        self.assertEqual(report(*args), report(*copy.deepcopy(args)))

    def test_actual_model_body_observed_without_network(self):
        import sys
        import types
        from unittest.mock import patch
        from offline_rag_metrics import run_graph_with_capture
        body = {"model": "synthetic", "messages": [{"role": "user", "content": "actual synthetic prompt"}]}
        calls = []
        client = types.SimpleNamespace(post=lambda url, **kw: calls.append((url, kw)) or "synthetic-response")
        llm = types.ModuleType("app.providers.llm"); original = lambda *a: client
        llm._ollama_client = original
        def answer(question, evidence):
            llm._ollama_client("synthetic", 1).post("/api/chat", json=body)
            return types.SimpleNamespace(claims=[])
        graph = types.ModuleType("qa_graph")
        graph.get_llm_provider = lambda: types.SimpleNamespace(name="ollama", answer=answer)
        graph.run_graph = lambda initial: {"candidate": graph.get_llm_provider().answer("question", [])}
        providers = types.ModuleType("app.providers"); providers.llm = llm
        services = types.ModuleType("app.services"); services.qa_graph = graph
        app = types.ModuleType("app"); app.services = services; app.providers = providers
        with patch.dict(sys.modules, {"app": app, "app.services": services, "app.providers": providers, "app.providers.llm": llm}):
            state = run_graph_with_capture({})
        self.assertEqual(state["offline_model_requests"][0]["json"], body)
        self.assertEqual(calls, [("/api/chat", {"json": body})])
        self.assertIs(llm._ollama_client, original)

    def test_bypassed_model_keeps_empty_observed_requests(self):
        import sys
        import types
        from unittest.mock import patch
        from offline_rag_metrics import run_graph_with_capture
        graph = types.ModuleType("qa_graph"); graph.get_llm_provider = lambda: None
        graph.run_graph = lambda initial: {"outcome": "escalate"}
        services = types.ModuleType("app.services"); services.qa_graph = graph
        app = types.ModuleType("app"); app.services = services
        with patch.dict(sys.modules, {"app": app, "app.services": services}):
            state = run_graph_with_capture({})
        self.assertEqual(state["offline_model_requests"], [])
        self.assertNotIn("offline_provider_input", state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
