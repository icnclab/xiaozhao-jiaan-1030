"""Recall baseline preparation/re-scoring. Standard library + offline metrics only.
Never imports app, loads .env, connects to DB, runs search or invokes a model.
"""
import argparse
import hashlib
import json
from pathlib import Path
from offline_rag_metrics import digest, evaluate, snapshots, stage, unavailable, VERSION

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "quality_tests/recall_round1"
METRICS = ("candidate_context_recall", "gate_context_recall", "selected_context_recall")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def historical_snapshot(actual):
    if "offline_snapshots" in actual:
        return actual["offline_snapshots"], "unknown"
    checks = actual.get("checks", {})
    searched = bool(actual.get("retrieval_result")) or "retrieve" in actual.get("timings_ms", {})
    blocked = bool(checks.get("risk_codes")) and not searched
    state = {"checks": checks}
    if searched:
        state["retrieved"] = actual.get("retrieval_result", [])
    saved = snapshots(state)
    saved["selected_evidence"] = stage(reason="exact_selected_text_not_saved; IDs_only_are_not_a_context_snapshot")
    saved["selection_ids"] = stage(list(actual.get("evidence_refs", {}).values()), provenance="historical_evidence_refs; not_model_input")
    saved["retrieval_execution"] = stage(True if searched else False if blocked else None,
                                          provenance="saved_retrieval_rows_or_timing_and_risk_codes")
    return saved, "search_executed" if searched else "safety_blocked_without_search" if blocked else "search_execution_unconfirmed"


def score_case(case, observation, annotation):
    snapshot = observation["snapshot"]
    reason = None
    if case.get("review_status") != "approved" or not case.get("reviewer") or not case.get("reviewed_at"):
        reason = "case_pending_human_review"
    elif case.get("applicability") != "home_care_confirmed":
        reason = "document_version_or_facility_not_confirmed_applicable"
    elif not case.get("required_facts"):
        reason = "required_facts_not_annotated"
    elif not all(f.get("id") and f.get("text") and f.get("references") and all(
            r.get("document") and r.get("version") and r.get("locator") for r in f["references"])
            for f in case["required_facts"]):
        reason = "fact_source_document_version_locator_missing"
    elif observation.get("question") != case.get("question"):
        reason = "observation_question_mismatch"
    elif snapshot.get("retrieval_execution", {}).get("items") is not True:
        reason = "retrieval_not_executed_or_unconfirmed"
    elif not annotation or annotation.get("method") != "human_review":
        reason = "human_stage_judgements_missing"
    elif annotation.get("case_sha256") != digest(case):
        reason = "annotation_case_mismatch"
    elif [(f.get("id"), f.get("text")) for f in annotation.get("required_facts", [])] != [
            (f["id"], f["text"]) for f in case["required_facts"]]:
        reason = "annotation_required_facts_mismatch"
    if reason:
        return {k: unavailable(reason) for k in METRICS}
    raw = evaluate(snapshot, annotation)
    return {k: raw[k] for k in METRICS}


def losses(metrics):
    # Report observations only; does not touch the project's Failure Type taxonomy.
    if any(metrics[k]["rate"] is None for k in METRICS):
        return {"status": "cannot_localize_without_complete_reviewed_stages"}
    details = [metrics[k]["details"] for k in METRICS]
    found = []
    for a, b, c in zip(*details):
        flags = (a["supported"], b["supported"], c["supported"])
        label = ("search_did_not_cover_fact" if not flags[0] else
                 "gate_excluded_fact" if not flags[1] else
                 "selection_omitted_fact" if not flags[2] else "selected_fact")
        found.append({"fact_id": a["id"], "observation": label})
    return {"status": "reviewed", "facts": found}


def report(dataset, observations, annotations):
    ids = [c["id"] for c in dataset["cases"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate dataset IDs")
    rows = []
    for case in dataset["cases"]:
        observed = observations["cases"].get(case["id"], {
            "question": case["question"], "snapshot": {}, "execution": "snapshot_missing"})
        metrics = score_case(case, observed, annotations.get(case["id"]))
        rows.append({"id": case["id"], "review_status": case["review_status"],
                     "execution": observed.get("execution"), "metrics": metrics,
                     "stage_observations": losses(metrics),
                     "provider_context": observed["snapshot"].get("generation_context", stage(reason="not_recorded")),
                     "model_input": observed["snapshot"].get("model_requests", stage(reason="actual_model_request_not_saved"))})
    cohort = [r for r in rows if all(r["metrics"][k]["rate"] is not None for k in METRICS)]
    stats = {}
    for key in METRICS:
        n = sum(r["metrics"][key]["numerator"] for r in cohort)
        d = sum(r["metrics"][key]["denominator"] for r in cohort)
        stats[key] = {"numerator": n if cohort else None, "denominator": d if cohort else None,
                      "rate": n/d if d else None, "reason": None if d else "no_common_reviewed_measurable_cohort"}
    return {"schema_version": 1, "evaluator_version": VERSION, "run_mode": "saved_files_only_no_search_no_model",
            "dataset_sha256": digest(dataset), "observations_sha256": digest(observations),
            "annotations_sha256": digest(annotations), "case_count": len(rows),
            "approved_count": sum(c.get("review_status") == "approved" for c in dataset["cases"]),
            "common_measurable_case_count": len(cohort), "statistics": stats, "results": rows,
            "limitations": ["Historical traces are not a current-code search baseline.",
                            "No model was called during this run; missing historical input stays unknown.",
                            "Common A/B/C cohort only; excluded cases are never scored as zero."]}


def prepare(root):
    paths = ["quality_tests/v1/gold_dataset_v1.json", "quality_tests/v1/baseline_report.json",
             "quality_tests/v1/calibration_set.json", "quality_tests/v1/reports/20261011-143121-084792/results.json"]
    gold, baseline, calibration, saved = [read(root/p) for p in paths]
    source_hashes = {p: file_hash(root/p) for p in paths}
    old = {r["id"]: r for r in baseline["results"]}
    cases = []; observations = {}
    for record in gold["records"]:
        correction = record["reviewed_correction"]
        question = record["qa_snapshot"]["question"]
        refs = [{"document": s.get("document_title"), "version": s.get("version_label"),
                 "version_id": s.get("version_id"), "locator": s.get("locator"),
                 "published_status_in_saved_record": s.get("version_status"),
                 "effective_from": s.get("effective_from"), "effective_to": s.get("effective_to")}
                for s in record["qa_snapshot"].get("sources", [])]
        case = {"id": "R-" + record["id"], "question": question,
                "origin": {"file": paths[0], "record_id": record["id"], "sha256": source_hashes[paths[0]],
                           "kind": "existing_reviewed_feedback; no_new_question_wording"},
                "prior_review": {"status": record.get("status"), "gold_readiness": record.get("gold_readiness"),
                                 "evidence_checked": correction.get("evidence_checked"),
                                 "approved_at": correction.get("gold_approved_at")},
                "expected_behavior": correction.get("expected_behavior"),
                "basis_type": correction.get("evidence_basis_type"),
                "required_facts": [], "required_facts_draft_verbatim": correction.get("correct_answer"),
                "source_reference_draft": {"document": correction.get("correct_source_document"),
                                           "locator": correction.get("correct_source_page_or_section")},
                "saved_reference_versions": refs, "target_facility": "home_care",
                "applicability": "pending_version_and_home_care_review", "review_status": "pending",
                "reviewer": None, "reviewed_at": None,
                "review_todo": "Verify source version/home-care scope; split necessary facts and review A/B/C entailment against exact snapshot."}
        cases.append(case)
        actual = old[record["id"]]["actual"]
        snapshot, execution = historical_snapshot(actual)
        observations[case["id"]] = {"question": old[record["id"]]["question"], "snapshot": snapshot,
                                    "execution": execution, "origin": paths[1], "source_sha256": source_hashes[paths[1]]}
    saved_rows = {r["id"]: r for r in saved["results"]}
    for original in calibration["cases"]:
        if original["id"] not in ("C003", "C014"):
            continue
        row = saved_rows[original["id"]]
        snapshot, execution = historical_snapshot(row)
        case = {"id": "R-" + original["id"], "question": original["question"],
                "origin": {"file": paths[2], "record_id": original["id"], "sha256": source_hashes[paths[2]],
                           "kind": "existing_calibration_case_with_saved_result; not_claimed_real_staff_interview"},
                "prior_review": {"human_review_required": original.get("human_review_required"), "saved_pass": row.get("pass_result")},
                "expected_behavior": original["expected_behavior"], "basis_type": "existing_test_expected_source",
                "required_facts": [], "required_facts_draft_verbatim": original["expected_answer_summary"],
                "source_reference_draft": original["expected_source_keywords"],
                "saved_reference_versions": [{"document": s.get("document_name"), "version": None,
                    "version_id": s.get("version_id"), "locator": s.get("page_or_section")} for s in row.get("source", [])],
                "target_facility": "home_care", "applicability": "pending_version_and_home_care_review",
                "review_status": "pending", "reviewer": None, "reviewed_at": None,
                "review_todo": "Verify original expected answer, exact document version and atomic facts; saved pass is not human recall review."}
        cases.append(case)
        observations[case["id"]] = {"question": row["question"], "snapshot": snapshot, "execution": execution,
                                    "origin": paths[3], "source_sha256": source_hashes[paths[3]]}
    return ({"schema_version": 1, "target_count": 20, "purpose": "home_care_recall_round1_preparation",
             "source_hashes": source_hashes, "cases": cases}, {"schema_version": 1, "cases": observations})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--directory", type=Path, default=DEFAULT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    folder = args.directory
    if args.prepare:
        folder.mkdir(parents=True, exist_ok=True)
        if any((folder/name).exists() for name in ("dataset.json", "observations.json", "annotations.json")):
            raise SystemExit("Refusing to overwrite prepared data/reviews; use a new directory")
        dataset, observations = prepare(ROOT)
        for name, data in (("dataset.json", dataset), ("observations.json", observations), ("annotations.json", {"schema_version": 1, "cases": {}})):
            (folder/name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    dataset = read(folder/"dataset.json"); observations = read(folder/"observations.json")
    annotations = read(folder/"annotations.json")["cases"]
    output = args.output or folder/"report.json"
    if output.exists():
        raise SystemExit("Refusing to overwrite report; choose a new --output")
    data = report(dataset, observations, annotations)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: data[k] for k in ("case_count", "approved_count", "common_measurable_case_count", "statistics")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
