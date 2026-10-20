"""Offline annotation-based metrics. Standard library only; never calls DB/providers.
Judgements are bound to an exact snapshot digest; no similarity-based entailment.
"""
import hashlib
import json
from dataclasses import asdict, is_dataclass

VERSION = "offline-rag-1.1"
METHOD = "reviewed_atomic_annotations_bound_to_snapshot; no automated semantic judge"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     default=str).encode()).hexdigest()


def stage(items=None, reason=None, provenance=None):
    return dict(items=items, reason=reason, provenance=provenance)


def serialize(value):
    def convert(item):
        if is_dataclass(item):
            return convert(asdict(item))
        if isinstance(item, dict):
            return {str(k): convert(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(v) for v in item]
        return item
    return json.loads(json.dumps(convert(value), default=str))


def snapshots(state, display_claims=None, sources=None, safety_notice=None):
    """Capture only observed state; never retrieve or infer provider inputs."""
    def observed(key):
        return stage(serialize(state[key]), provenance="graph_final_state:" + key) if key in state else stage(reason="stage_not_observed")
    candidates = observed("retrieved")
    gate = state.get("checks", {}).get("retrieval_gate")
    admitted = None if gate is None else set(gate.get("admitted_chunk_ids", []))
    gated = stage(reason="gate_snapshot_missing")
    if admitted is not None and candidates["items"] is not None:
        rows = [c for c in candidates["items"] if str(c["chunk_id"]) in admitted]
        gated = stage(rows, provenance="persisted_gate_ids_join_observed_candidates") if {str(c["chunk_id"]) for c in rows} == admitted else stage(reason="gate_sources_incomplete")
    candidate = state.get("candidate")
    return dict(safety_notice=stage(safety_notice, provenance="answer_assembly_policy_notice") if safety_notice is not None else stage(reason="stage_not_observed"),
                candidate_evidence=candidates, gate_evidence=gated,
                prepared_evidence=observed("evidence"),
                selected_evidence=observed("evidence"),
                generation_context=observed("offline_provider_input"),
                provider_question=observed("offline_provider_question"),
                model_requests=observed("offline_model_requests"),
                generation_candidate_claims=observed("offline_provider_claims"),
                post_generation_candidate_claims=stage(serialize(candidate.claims), provenance="graph_candidate_after_fact_enrichment") if candidate is not None else stage(reason="stage_not_observed"),
                verified_claims=observed("claims"),
                display_claims=stage(serialize(display_claims), provenance="answer_assembly") if display_claims is not None else stage(reason="stage_not_observed"),
                cited_sources=stage(serialize(sources), provenance="display_claim_actual_refs") if sources is not None else stage(reason="stage_not_observed"))


def unavailable(reason, details=None):
    return dict(numerator=None, denominator=None, rate=None, reason=reason, details=details or [])


def aggregate(details):
    if not details:
        return unavailable("zero_denominator")
    if any(d["supported"] is None for d in details):
        return unavailable("incomplete_judgements", details)
    n = sum(d["supported"] for d in details)
    return dict(numerator=n, denominator=len(details), rate=n/len(details), reason=None, details=details)


def judgement(item, key, rows, cited=None):
    j = item.get(key)
    result = dict(id=item.get("id"), text=item.get("text"), supported=None,
                  missing=None, evidence_sources=[], errors=[], reason=None)
    if not isinstance(j, dict) or not isinstance(j.get("supported"), bool):
        result["reason"] = "judgement_missing"
        return result
    ids = j.get("source_ids", [])
    sources = {str(r.get("chunk_id")): r for r in rows}
    if any(str(i) not in sources for i in ids):
        result["reason"] = "judgement_source_not_in_snapshot"
        return result
    if j["supported"] and (not ids or any(sources[str(i)].get("applicable") is False for i in ids)):
        result["reason"] = "support_sources_missing_or_inapplicable"
        return result
    if cited is not None and j["supported"] and any(str(i) not in cited for i in ids):
        result["reason"] = "support_not_from_actual_citation"
        return result
    result.update(supported=j["supported"], missing=not j["supported"],
                  evidence_sources=[sources[str(i)] for i in ids], errors=j.get("errors", []))
    return result


def evaluate(snapshot, annotation=None, outcome="answer"):
    names = ("candidate_context_recall", "selected_context_recall", "faithfulness", "citation_support",
             "gate_context_recall")
    result = dict(evaluator_version=VERSION, annotation_version=(annotation or {}).get("annotation_version"),
                  method=METHOD, snapshot_sha256=digest(snapshot), excluded_claims=[])
    def all_missing(reason):
        result.update({n: unavailable(reason) for n in names})
        return result
    if annotation is None:
        return all_missing("annotation_missing")
    if not annotation.get("annotation_version") or annotation.get("method") not in ("human_review", "synthetic"):
        return all_missing("annotation_metadata_invalid")
    if annotation.get("snapshot_sha256") != digest(snapshot):
        return all_missing("annotation_snapshot_mismatch")
    facts = annotation.get("required_facts")
    # Legacy snapshots with only an observed provider context remain readable.
    # A present-but-missing selected stage must never be replaced by a guessed input.
    selected_key = next((k for k in ("selected_evidence", "prepared_evidence", "generation_context") if k in snapshot), "selected_evidence")
    for name, key, review in ((names[0], "candidate_evidence", "candidate"),
                              (names[4], "gate_evidence", "gate"), (names[1], selected_key, "selected")):
        rows = snapshot.get(key, {}).get("items")
        if facts is None:
            result[name] = unavailable("required_facts_not_annotated")
        elif rows is None:
            result[name] = unavailable("evidence_snapshot_missing:" + key,
                                       [dict(id=f.get("id"), text=f.get("text"), supported=None, missing=None,
                                             evidence_sources=[], reason="evidence_snapshot_missing") for f in facts])
        else:
            result[name] = aggregate([judgement(f, review, rows) for f in facts])
    claims = annotation.get("atomic_claims")
    display = snapshot.get("display_claims", {}).get("items")
    for name, key, review in ((names[2], "generation_context", "context"), (names[3], "cited_sources", "citation")):
        rows = snapshot.get(key, {}).get("items")
        if outcome != "answer":
            result[name] = unavailable("not_applicable:" + outcome)
        elif claims is None:
            result[name] = unavailable("atomic_claims_not_annotated")
        elif display is None or rows is None:
            result[name] = unavailable("claim_or_evidence_snapshot_missing:" + key)
        elif annotation.get("claim_decomposition_complete") is not True:
            result[name] = unavailable("claim_decomposition_not_confirmed_complete")
        else:
            details = []
            excluded = []
            covered = set()
            for c in claims:
                index = c.get("display_claim_index")
                if not isinstance(index, int) or index < 0 or index >= len(display):
                    details.append(dict(id=c.get("id"), supported=None, reason="invalid_display_claim_index"))
                    continue
                covered.add(index)
                kind = c.get("kind")
                if kind in ("safety_notice", "policy_declaration"):
                    excluded.append(dict(id=c.get("id"), kind=kind))
                    continue
                if kind != "kb_fact":
                    details.append(dict(id=c.get("id"), supported=None, reason="claim_kind_missing"))
                    continue
                refs = display[index].get("refs", [])
                cited = {str(r.get("chunk_id")) for r in rows if r.get("ref") in refs}
                detail = judgement(c, review, rows, cited if review == "citation" else None)
                if review == "citation" and (not refs or any(ref not in {r.get("ref") for r in rows} for ref in refs)):
                    detail.update(supported=False, missing=True, reason="nonexistent_or_missing_citation", errors=["nonexistent_reference"])
                details.append(detail)
            result["excluded_claims"] = excluded
            result[name] = aggregate(details) if covered == set(range(len(display))) else unavailable("unannotated_display_claims", details)
    return result


def load_sidecar(path):
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("cases"), dict):
        raise ValueError("Invalid offline annotation sidecar")
    return data["cases"]


def attach(rows, annotations):
    for row in rows:
        actual = row.get("actual", row)
        row["offline_rag_metrics"] = evaluate(actual.get("offline_snapshots", {}),
                                             annotations.get(row["id"]), actual.get("outcome", "answer"))
    return rows


def run_graph_with_capture(initial):
    """Single-process offline replay only. Observe actual provider call unchanged.
    Scoped extractive paths that bypass provider stay missing, never fabricated.
    No runtime import occurs unless the explicitly requested replay invokes this.
    """
    from unittest.mock import patch
    from app.services import qa_graph
    original_factory = qa_graph.get_llm_provider
    observed = {"offline_model_requests": []}

    class Observer:
        def __init__(self, provider):
            self.provider = provider

        def answer(self, question, evidence):
            observed["offline_provider_question"] = serialize(question)
            observed["offline_provider_input"] = serialize(evidence)
            if getattr(self.provider, "name", None) == "ollama":
                from app.providers import llm
                original_client = llm._ollama_client

                class ClientObserver:
                    def __init__(self, client):
                        self.client = client

                    def post(self, url, *args, **kwargs):
                        # Capture the actual body passed to HTTP, not a rebuilt prompt.
                        observed["offline_model_requests"].append({
                            "provider": "ollama", "path": str(url), "json": serialize(kwargs.get("json")),
                            "provenance": "offline_intercept_actual_client_post; request_attempt_not_success"})
                        return self.client.post(url, *args, **kwargs)

                    def __getattr__(self, name):
                        return getattr(self.client, name)

                with patch.object(llm, "_ollama_client", lambda *a, **kw: ClientObserver(original_client(*a, **kw))):
                    candidate = self.provider.answer(question, evidence)
            else:
                candidate = self.provider.answer(question, evidence)
            observed["offline_provider_claims"] = serialize(candidate.claims)
            return candidate

    with patch.object(qa_graph, "get_llm_provider", lambda: Observer(original_factory())):
        state = qa_graph.run_graph(initial)
    state.update(observed)
    return state
