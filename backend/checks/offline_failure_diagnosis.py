"""Reviewed offline failure attribution. No runtime app imports or database access."""
import ast
import csv
import json
from pathlib import Path

try:
    from .offline_rag_metrics import digest
except ImportError:
    from offline_rag_metrics import digest

VERSION = "offline-failure-1.0"
METHOD = "snapshot_and_trace_bound_reviewed_attribution; metrics_are_not_root_cause_proof"
ROOT = Path(__file__).resolve().parents[2]

# Only existing components. Requirements intentionally conservative. Missing
# ingestion/vector instrumentation cannot be substituted by low recall.
STAGES = {
    "query_processing": {"snapshots": [], "trace": ["query_understanding"]},
    "chunking": {"snapshots": ["candidate_evidence"], "trace": ["chunking_diagnostics"]},
    "embedding": {"snapshots": ["candidate_evidence"], "trace": ["embedding_diagnostics"]},
    "top_k": {"snapshots": ["gate_evidence", "prepared_evidence"], "trace": ["evidence_selection"]},
    "evidence_gate": {"snapshots": ["candidate_evidence", "gate_evidence"], "trace": ["retrieval_gate"]},
    "evidence_selection": {"snapshots": ["gate_evidence", "prepared_evidence"], "trace": ["evidence_selection"]},
    "generation": {"snapshots": ["generation_context", "generation_candidate_claims",
                                 "post_generation_candidate_claims", "verified_claims", "display_claims"], "trace": []},
    "answer_presentation": {"snapshots": ["verified_claims", "display_claims"], "trace": []},
    "citation_verification": {"snapshots": ["generation_context", "verified_claims", "display_claims", "cited_sources"], "trace": ["claims"]},
    "safety_routing": {"snapshots": [], "trace": ["risk_codes"]},
}
COLUMNS = ["case_id", "error_type", "failure_stage", "failure_cause", "diagnosis_status",
           "evidence", "before_metrics", "change", "after_metrics"]


def existing_error_types():
    """Read canonical Literal statically; never import production feedback module.
    No replacement registry is maintained here.
    """
    path = ROOT / "backend/app/services/quality_feedback.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ErrorType" for t in node.targets):
            value = node.value
            if not isinstance(value, ast.Subscript) or not isinstance(value.value, ast.Name) or value.value.id != "Literal":
                raise ValueError("Canonical ErrorType must be Literal")
            values = ast.literal_eval(value.slice)
            if not isinstance(values, tuple) or not all(isinstance(v, str) for v in values):
                raise ValueError("Invalid canonical ErrorType")
            return frozenset(values)
    raise ValueError("Canonical ErrorType not found")


def load_diagnoses(path):
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("cases"), dict):
        raise ValueError("Invalid failure diagnosis sidecar")
    return data["cases"]


def lookup(value, path):
    for part in path:
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and isinstance(part, int) and 0 <= part < len(value):
            value = value[part]
        else:
            raise ValueError("Evidence path not observed")
    return value


def metrics_observation(row, snapshot):
    metrics = row.get("offline_rag_metrics", {})
    keys = ("candidate_context_recall", "selected_context_recall", "faithfulness", "citation_support")
    if metrics.get("snapshot_sha256") == digest(snapshot) and metrics.get("evaluator_version") and metrics.get("annotation_version") and any(metrics.get(k, {}).get("rate") is not None for k in keys):
        return dict(status="measured", snapshot_id=digest(snapshot), evaluator_version=metrics["evaluator_version"],
                    annotation_version=metrics["annotation_version"], values={k: {f: metrics.get(k, {}).get(f) for f in ("numerator", "denominator", "rate", "reason")} for k in keys})
    return dict(status="not_tested", reason="no_snapshot_bound_annotated_measurement", values=None)


def diagnose(row, annotation=None, error_types=None):
    actual = row.get("actual", row)
    snapshot = actual.get("offline_snapshots", {})
    trace = actual.get("checks", {})
    snapshot_id = digest(snapshot) if snapshot else None
    trace_id = digest(trace) if trace else None
    types = existing_error_types() if error_types is None else error_types
    reported_error = (annotation or {}).get("error_type", row.get("error_type"))
    error = reported_error if reported_error in types else None
    review = (annotation or {}).get("human_review", {})
    base = dict(case_id=row.get("id"), error_type=error, failure_stage=None, failure_cause=None,
                diagnosis_status="undetermined", evidence=[], evaluator_version=VERSION, method=METHOD,
                annotation_version=(annotation or {}).get("annotation_version"), snapshot_id=snapshot_id,
                trace_id=trace_id, human_review=dict(review, required=True),
                before_metrics=metrics_observation(row, snapshot),
                change=(annotation or {}).get("change") or dict(status="not_changed", description=None),
                after_metrics=dict(status="not_tested", reason="no_verified_post_change_replay", values=None),
                is_failure=None, reason=None)
    def undetermined(reason, **extra):
        return [dict(base, reason=reason, **extra)]

    # A routing reason is never itself an error label. Correct safety/clarify
    # decisions are not failures, even though they have an escalation reason.
    expected = row.get("expected_behavior")
    observed = row.get("actual_behavior", actual.get("behavior", actual.get("outcome")))
    passed = row.get("automated_pass", row.get("pass_result"))
    if expected in ("refuse", "risk_block", "escalate", "clarify") and observed == expected and passed is True:
        return undetermined("expected_safe_or_clarification_route", is_failure=False, error_type=None)
    if annotation is None:
        return undetermined("diagnosis_annotation_missing")
    if error is None:
        return undetermined("invalid_or_missing_error_type", reported_error_type=reported_error)
    if not trace or not snapshot or not any(isinstance(v, dict) and v.get("items") is not None for v in snapshot.values()):
        return undetermined("trace_or_snapshot_missing")
    if annotation.get("snapshot_sha256") != snapshot_id or annotation.get("trace_sha256") != trace_id:
        return undetermined("annotation_observation_mismatch")
    if not annotation.get("annotation_version") or not review.get("review_id") or review.get("method") not in ("human_review", "synthetic"):
        return undetermined("human_annotation_missing")
    if review.get("failure") is False:
        return undetermined("reviewed_non_failure", is_failure=False, error_type=None)
    if review.get("failure") is not True:
        return undetermined("failure_not_established")
    causes = annotation.get("causes", [])
    if not causes:
        return undetermined("no_evidenced_cause", is_failure=True)
    results = []
    for cause in causes:
        stage = cause.get("failure_stage")
        reason = None
        proof = []
        requirements = STAGES.get(stage)
        if requirements is None:
            reason = "unimplemented_or_unknown_stage"
        elif not cause.get("failure_cause") or not cause.get("rationale"):
            reason = "cause_or_rationale_missing"
        elif any(snapshot.get(k, {}).get("items") is None for k in requirements["snapshots"]):
            reason = "stage_snapshot_missing"
        elif any(k not in trace for k in requirements["trace"]):
            reason = "stage_trace_missing"
        else:
            for ref in cause.get("evidence", []):
                try:
                    kind = ref.get("kind")
                    path = ref.get("path", [])
                    if kind not in ("snapshot", "trace") or not path:
                        raise ValueError("Metric-only evidence cannot establish cause")
                    value = lookup(snapshot if kind == "snapshot" else trace, path)
                    if value is None or ref.get("sha256") != digest(value) or not ref.get("finding"):
                        raise ValueError("Evidence missing or mismatch")
                    # Require stage-local records, not an unrelated available trace.
                    if kind == "snapshot" and path[0] not in requirements["snapshots"]:
                        raise ValueError("Evidence unrelated to stage")
                    if kind == "trace" and path[0] not in requirements["trace"]:
                        raise ValueError("Evidence unrelated to stage")
                    proof.append(dict(ref, observation_id=snapshot_id if kind == "snapshot" else trace_id))
                except (ValueError, TypeError, KeyError):
                    reason = "invalid_or_unrelated_evidence"
                    break
            covered_snapshot = {p["path"][0] for p in proof if p["kind"] == "snapshot"}
            covered_trace = {p["path"][0] for p in proof if p["kind"] == "trace"}
            if reason is None and (not proof or not set(requirements["snapshots"]) <= covered_snapshot or not set(requirements["trace"]) <= covered_trace):
                reason = "insufficient_stage_evidence"
        status = cause.get("diagnosis_status")
        if reason is None and status not in ("confirmed", "suspected"):
            reason = "invalid_diagnosis_status"
        if reason is None and status == "confirmed" and review.get("status") != "approved":
            reason = "confirmation_requires_approved_review"
        if reason:
            results.append(dict(base, is_failure=True, reason=reason,
                                proposed_stage=stage, proposed_cause=cause.get("failure_cause"), evidence=proof))
        else:
            results.append(dict(base, is_failure=True, failure_stage=stage, failure_cause=cause["failure_cause"],
                                diagnosis_status=status, evidence=proof, rationale=cause["rationale"], reason=None,
                                human_review=dict(review, required=status != "confirmed")))
    return results


def attach_diagnoses(rows, annotations=None):
    annotations = annotations or {}
    types = existing_error_types()
    for row in rows:
        row["offline_failure_diagnoses"] = diagnose(row, annotations.get(row["id"]), types)
    return rows


def write_improvement_reports(directory, rows):
    """Add separate artifacts only. Never overwrite historical reports."""
    directory = Path(directory)
    records = [d for r in rows for d in r.get("offline_failure_diagnoses", [])]
    paths = [directory / ("failure_cases." + ext) for ext in ("json", "csv", "md")]
    if any(p.exists() for p in paths):
        raise FileExistsError("Failure report already exists; use a new output directory")
    report = dict(evaluator_version=VERSION, method=METHOD, results=records,
                  limitations=["Metrics alone do not prove root causes", "Before/after never imputed", "Reviewed attribution is not an automatic semantic diagnosis"])
    with paths[0].open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with paths[1].open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS + ["snapshot_id", "trace_id", "evaluator_version", "annotation_version", "human_review", "is_failure", "reason"])
        writer.writeheader()
        for record in records:
            writer.writerow({k: json.dumps(record.get(k), ensure_ascii=False) if isinstance(record.get(k), (dict, list)) else record.get(k) for k in writer.fieldnames})
    def cell(value):
        if isinstance(value, dict) and value.get("status") == "not_tested":
            return "??"
        return (json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value if value is not None else "?")).replace("|", "?").replace("\n", " ").replace("\r", " ")
    lines = ["# ????????", "", VERSION + "?" + METHOD, "",
             "?????? is_failure=false?undetermined ???????????????? after_metrics ????", "",
             "| " + " | ".join(COLUMNS) + " |", "| " + " | ".join(["---"] * len(COLUMNS)) + " |"]
    lines += ["| " + " | ".join(cell(r.get(k)) for k in COLUMNS) + " |" for r in records]
    lines += ["", "?????trace ID???????????????? failure_cases.json?"]
    with paths[2].open("x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
