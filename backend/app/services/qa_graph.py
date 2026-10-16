"""問答流程：LangGraph StateGraph。

節點與分支寫死（確定性編排），每一步的結果都放進 state 供稽核：

    deidentify → screen_risk ─┬→ escalate
                              └→ retrieve ─┬→ escalate（無依據）
                                           └→ generate ─┬→ escalate（LLM 失敗）
                                                        └→ verify ─┬→ answer
                                                                   └→ escalate

授權（authorize）在 API 層完成，進圖前 state 已帶驗證過的 user/org。
圖本身不寫資料庫；持久化由 qa_service 在同一交易完成。
"""

from __future__ import annotations

import time
import uuid
from datetime import date
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.providers.llm import CandidateAnswer, EvidenceItem, get_llm_provider
from app.services.deid import deidentify
from app.services.evidence_sufficiency import (
    answers_supported_penalty_amount,
    asks_evaluation_outcome_prediction,
    asks_penalty_amount,
    supported_penalty_amounts,
)
from app.services.qa_policy import DEFAULT_POLICY, QaPolicy, looks_like_injection, screen_risk
from app.services.retrieval import RetrievedChunk, retrieve
from app.services.retrieval_gate import assess_evidence
from app.services.query_understanding import clarification_reason, clarification_prompt, normalize_colloquial, medication_admin_intent, purchasing_rule_intent
from app.services.evidence_selection import prioritize_admitted, requested_field, answers_requested_value
from app.services.role_consistency import check_roles
from app.services.text import bigrams, extract_quantities, support_score

REASON_TEXT = {
    "risk_emergency": "可能是緊急狀況，系統不提供處置建議",
    "risk_clinical": "涉及臨床判斷，系統不提供建議",
    "risk_medication": "涉及用藥，系統不提供建議",
    "risk_subsidy_amount": "涉及補助或費用金額，系統不做試算或承諾",
    "no_evidence": "知識庫中找不到足夠依據",
    "llm_error": "AI 產生回答時發生錯誤",
    "llm_format": "AI 回答格式不正確",
    "insufficient": "依據不足或適用條件不明",
    "citation_missing": "回答缺少可對應的出處",
    "unsupported_claim": "回答內容無法被引用條文支持",
    "conflict": "不同文件的規定不一致",
    "output_risk": "回答涉及臨床或用藥內容",
    "suspicious_content": "檢索到的文件含可疑指令",
}
from app.services.public_messages import RISK_LABELS
REASON_TEXT.update({f'risk_{code}': label for code, label in RISK_LABELS.items()})
REASON_TEXT['no_evidence'] = '找不到足夠資料'


class QaState(TypedDict, total=False):
    """問答流程狀態。`question_raw` 只存在於記憶體，不寫入資料庫或日誌。"""

    session: Session
    org_id: uuid.UUID
    facility_type: str
    today: date
    question_raw: str
    deid_terms: set[tuple[str, int]]
    policy: QaPolicy
    question_masked: str
    deid_hits: dict[str, int]
    risk_codes: list[str]
    retrieved: list[RetrievedChunk]
    evidence: list[EvidenceItem]
    evidence_map: dict[str, RetrievedChunk]
    candidate: CandidateAnswer
    checks: dict[str, Any]
    outcome: str
    reason: str | None
    reason_detail: str | None
    claims: list[dict[str, Any]]
    timings_ms: dict[str, int]


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def node_deidentify(state: QaState) -> QaState:
    """去識別化：之後所有節點只看遮罩後文字。"""
    result = deidentify(normalize_colloquial(state["question_raw"]), state.get("deid_terms"))
    return {"question_masked": result.text, "deid_hits": result.hits, "checks": {"deid_hits": result.hits}}



def _needs_clarification(question: str) -> bool:
    """判斷問題是否只有代名詞／省略語境，無法知道使用者實際在問什麼。"""
    q = question.strip().replace("？", "").replace("?", "")
    if clarification_reason(question):
        return True

    vague_terms = (
        "這個", "這件事", "這樣", "那個", "那件事", "這種情況",
        "這要", "這需要", "這可以", "這能不能",
    )

    # 有明確領域詞時仍進正常 RAG，不因為句中含「這個」就攔截
    domain_terms = (
        "跌倒", "瘀青", "換藥", "傷口", "嗆", "進食", "吃飯",
        "服務紀錄", "紀錄", "異常事件", "通報",
        "服務計畫", "買藥", "用藥", "評鑑", "喘息", "就醫",
        "長照", "照服員", "照顧服務員", "家屬", "個案",
        "追蹤", "訪視", "申報", "法規", "規定",
    )

    has_vague = any(term in q for term in vague_terms)
    has_domain = any(term in q for term in domain_terms) or medication_admin_intent(q) or purchasing_rule_intent(q)

    # 非常短，而且只剩「可以嗎／怎麼辦／要不要」等，也視為缺上下文
    generic_only = (
        len(q) <= 12
        and any(term in q for term in ("可以嗎", "能不能", "怎麼辦", "要不要", "要怎麼做"))
        and not has_domain
    )

    return (has_vague and not has_domain) or generic_only


def node_clarify(state: QaState) -> QaState:
    """缺少必要上下文時先追問，不直接建立督導案件。"""
    # A terse emergency must still reach the existing risk screen. Clarification
    # cannot short-circuit a recognized risk before that screen runs.
    if screen_risk(state['question_masked'], state['policy']):
        return {}
    from app.services.qa_policy import clarification_decision
    decision = clarification_decision(state['question_masked'], state['policy'])
    if decision is not None:
        checks = dict(state.get('checks', {}), clarification=decision)
        if not decision['needed']:
            return {'checks': checks}
        return {'checks': checks, 'outcome': 'clarify', 'reason': 'need_context',
                'reason_detail': decision['prompt']}
    if not _needs_clarification(state["question_masked"]):
        return {}

    checks = dict(state.get("checks", {}))
    reason = clarification_reason(state['question_masked']) or 'unspecified_subject'
    checks["clarification"] = {"needed": True, "reason": reason, 'prompt': clarification_prompt(reason),
                               'policy_version': state['policy'].clarification_version,
                               'rule_code': 'legacy_missing_context'}

    return {
        "checks": checks,
        "outcome": "clarify",
        "reason": "need_context",
        "reason_detail": clarification_prompt(reason),
    }


def node_screen_risk(state: QaState) -> QaState:
    """規則式風險篩檢（臨床、用藥、補助金額、緊急）。"""
    rules = screen_risk(state["question_masked"], state["policy"])
    codes = [rule.code for rule in rules]
    checks = dict(state.get("checks", {}), risk_codes=codes)
    if codes:
        return {"risk_codes": codes, "checks": checks, "outcome": "escalate", "reason": f"risk_{codes[0]}"}
    return {"risk_codes": [], "checks": checks}


def node_retrieve(state: QaState) -> QaState:
    session = state["session"]
    """檢索並挑選證據；帶提示注入樣式的切塊排除在證據外。"""
    start = time.perf_counter()
    policy = state["policy"]
    results = retrieve(state["session"], state["question_masked"], state["org_id"], state["facility_type"],
                       state["today"], policy)
    timings = dict(state.get("timings_ms", {}), retrieve=_ms(start))
    flagged = [r for r in results if r.injection_flag]
    decisions = {r.chunk_id: assess_evidence(state['question_masked'], r, policy) for r in results}
    clean = [r for r in results if decisions[r.chunk_id].admitted]
    checks = dict(state.get("checks", {}))
    checks["retrieval"] = [
        {"chunk_id": str(r.chunk_id), "coverage": r.coverage, "vector": r.vector, "combined": r.combined,
         "hybrid_score": r.hybrid_score, "topic_relevance": r.topic_relevance,
         "title_bonus": r.title_bonus, "intent_bonus": r.intent_bonus,
         'normalized_coverage': r.normalized_coverage, 'normalized_hybrid_score': r.normalized_hybrid_score,
         "injection_flag": r.injection_flag}
        for r in results[:8]
    ]
    checks["injection_chunks_excluded"] = [str(r.chunk_id) for r in flagged[:8]]
    checks['retrieval_gate'] = {
        'version': policy.version,
        'admitted_chunk_ids': [str(r.chunk_id) for r in clean],
        'candidates': [{'chunk_id': str(r.chunk_id), **decisions[r.chunk_id].audit()} for r in results],
    }
    top = clean[0] if clean else None
    if top is None:
        # 只有「注入切塊本身足以當證據、卻因可疑指令被排除」時才標 suspicious_content
        injected_relevant = any(
            assess_evidence(state['question_masked'], f, policy, check_injection=False).admitted for f in flagged
        )
        reason = "suspicious_content" if injected_relevant else "no_evidence"
        return {"retrieved": results, "checks": checks, "timings_ms": timings, "outcome": "escalate",
                "reason": reason}
    # Document focusing must not hide independently admitted conflicting rules.
    # The post-generation conflict/citation/support checks remain in place.
    conflict = detect_conflict(state['question_masked'], clean)
    if conflict:
        checks['conflict'] = conflict
        return {'retrieved': results, 'checks': checks, 'timings_ms': timings,
                'outcome': 'escalate', 'reason': 'conflict'}
    # 若 Top1 明顯領先其他文件，優先只提供同一文件的證據給 LLM，
    # 避免正確主來源被相似的手冊／函釋干擾。
    best_other = next(
        (r for r in clean[1:] if r.document_id != top.document_id),
        None,
    )

    focus_same_document = (
        top.combined >= 0.45
        and (
            best_other is None
            or (top.combined - best_other.combined) >= 0.05
        )
    )

    from app.services.query_understanding import record_intent
    checks['query_intent'] = 'record' if record_intent(state['question_masked']) else ('permission' if decisions[top.chunk_id].permission_intent else 'general')
    permission_gate = decisions[top.chunk_id].permission_intent or decisions[top.chunk_id].reporting_intent or record_intent(state['question_masked'])
    if permission_gate:
        # For permissions, only admitted topical rule chunks enter generation.
        # Do not auto-attach letterheads or technique-only adjacent paragraphs.
        chosen = [r for r in clean if not focus_same_document or r.document_id == top.document_id][:policy.top_k]
        checks['evidence_focus'] = {'enabled': focus_same_document, 'document_id': str(top.document_id),
                                    'title': top.title, 'selection': 'admitted_intent_rules'}
    elif focus_same_document:
        # 已高度確定主文件時，直接由 DB 補 Top1 前後相鄰段落。
        # 公文常把主旨放在第 1 段，真正判斷原則放在後續「說明」段落；
        # 這些段落可能沒有足夠關鍵字，因此不一定進原始 retrieval candidates。
        adjacent_rows = session.execute(
            text(
                """
                WITH anchor AS (
                    SELECT seq
                    FROM chunks
                    WHERE id = :chunk_id
                )
                SELECT
                    c.id AS chunk_id,
                    c.version_id,
                    c.text,
                    c.locator,
                    dv.document_id,
                    dv.version_label,
                    dv.effective_from,
                    dv.effective_to,
                    d.title,
                    d.doc_type
                FROM chunks c
                JOIN document_versions dv ON dv.id = c.version_id
                JOIN documents d ON d.id = dv.document_id
                CROSS JOIN anchor a
                WHERE c.version_id = :version_id
                ORDER BY ABS(c.seq - a.seq), c.seq
                LIMIT :k
                """
            ),
            {
                "chunk_id": top.chunk_id,
                "version_id": top.version_id,
                "k": policy.top_k,
            },
        ).all()

        chosen = []
        for row in adjacent_rows:
            injection = looks_like_injection(row.text)
            if injection:
                continue

            if row.chunk_id == top.chunk_id:
                coverage = top.coverage
                vector = top.vector
                combined = top.combined
            else:
                # 補入的相鄰段落不是靠檢索分數入選，因此不偽造分數。
                coverage = 0.0
                vector = 0.0
                combined = 0.0

            item = RetrievedChunk(
                    chunk_id=row.chunk_id,
                    version_id=row.version_id,
                    document_id=row.document_id,
                    title=row.title,
                    doc_type=row.doc_type,
                    locator=row.locator,
                    version_label=row.version_label,
                    effective_from=row.effective_from,
                    effective_to=row.effective_to,
                    text=row.text,
                    coverage=coverage,
                    vector=vector,
                    combined=combined,
                    injection_flag=False,
                )
            if row.chunk_id == top.chunk_id:
                item = top
            # Neighbours must independently contain topical body evidence;
            # adjacency and title cannot establish relevance.
            if row.chunk_id == top.chunk_id or assess_evidence(state['question_masked'], item, policy).body_topic >= policy.min_gate_body_topic:
                chosen.append(item)

        checks["evidence_focus"] = {
            "enabled": True,
            "document_id": str(top.document_id),
            "title": top.title,
            "top_score": top.combined,
            "best_other_score": best_other.combined if best_other else None,
        }
    else:
        chosen = [top] + [
            r for r in clean[1:]
            if r.combined >= policy.min_evidence_score
        ][: policy.top_k - 1]

        checks["evidence_focus"] = {
            "enabled": False,
        }

    previous_ids = [str(c.chunk_id) for c in chosen]
    chosen, fact_ids = prioritize_admitted(state['question_masked'], clean, chosen, policy.top_k)
    frontline = [item for item in clean if decisions[item.chunk_id].route == 'frontline_reporting_duty']
    if frontline:
        chosen = frontline[:policy.top_k]
    purchase_rules = [item for item in clean if decisions[item.chunk_id].route in ('purchasing_scope_table', 'administrative_scope_table')]
    if purchasing_rule_intent(state['question_masked']) and purchase_rules:
        chosen = purchase_rules[:policy.top_k]
    scope_ids = next((item.scope_chunk_ids for item in chosen if item.scope_chunk_ids), ())
    if scope_ids:
        # Cite each original table chunk separately, including scope and conditions.
        by_id = {item.chunk_id: item for item in results}
        chosen = [by_id[cid] for cid in scope_ids if cid in by_id][:policy.top_k]
        checks['administrative_scope_context'] = [str(item.chunk_id) for item in chosen]
    checks['evidence_selection'] = {'requested_field': requested_field(state['question_masked']),
        'fact_chunk_ids': fact_ids, 'previous_chunk_ids': previous_ids,
        'selected_chunk_ids': [str(c.chunk_id) for c in chosen]}
    evidence, evidence_map = [], {}
    for index, item in enumerate(chosen, start=1):
        ref = f"E{index}"
        evidence_map[ref] = item
        evidence.append(
            EvidenceItem(ref=ref, chunk_id=str(item.chunk_id), title=item.title, locator=item.locator,
                         version_label=item.version_label,
                         effective_from=item.effective_from.isoformat() if item.effective_from else "未填",
                         text=item.text)
        )
    timings["evidence_prepare"] = max(0, _ms(start) - timings["retrieve"])
    checks["evidence_size"] = {"chunks": len(evidence), "chars": sum(len(e.text) for e in evidence)}
    if asks_evaluation_outcome_prediction(state["question_masked"]):
        checks["evidence_sufficiency"] = {
            "required_fact": "actual_evaluation_outcome",
            "supporting_refs": [],
        }
        return {
            "retrieved": results,
            "evidence": evidence,
            "evidence_map": evidence_map,
            "checks": checks,
            "timings_ms": timings,
            "outcome": "escalate",
            "reason": "insufficient",
            "reason_detail": "現有證據僅能說明評鑑規則，無法預測特定機構實際評鑑結果",
        }

    if asks_penalty_amount(state["question_masked"]):
        amount_refs = [e.ref for e in evidence if supported_penalty_amounts(state["question_masked"], e.text)]
        checks["evidence_sufficiency"] = {"required_fact": "penalty_amount", "supporting_refs": amount_refs}
        if not amount_refs:
            return {"retrieved": results, "evidence": evidence, "evidence_map": evidence_map,
                    "checks": checks, "timings_ms": timings, "outcome": "escalate", "reason": "insufficient",
                    "reason_detail": "相關證據未提供所問的罰款或扣款金額"}
    return {"retrieved": results, "evidence": evidence, "evidence_map": evidence_map, "checks": checks,
            "timings_ms": timings}


def node_generate(state: QaState) -> QaState:
    """呼叫 LLM（或摘錄器）依證據產生候選回答。"""
    start = time.perf_counter()
    try:
        from app.services.answer_presentation import scoped_ba16_candidate
        candidate = scoped_ba16_candidate(state['question_masked'], state['evidence_map'])
        if candidate is None:
            candidate = get_llm_provider().answer(state["question_masked"], state["evidence"])
    except Exception as exc:  # 任何 provider 錯誤都走轉人工，不硬答
        timings = dict(state.get("timings_ms", {}), generate=_ms(start))
        checks = dict(state.get("checks", {}), llm_error=type(exc).__name__)
        return {"timings_ms": timings, "checks": checks, "outcome": "escalate", "reason": "llm_error"}
    timings = dict(state.get("timings_ms", {}), generate=_ms(start))
    checks = dict(state.get("checks", {}), llm_metrics=candidate.metrics)
    from app.services.answer_presentation import include_ba16_fact
    candidate = include_ba16_fact(state['question_masked'], state['evidence_map'], candidate)
    if not candidate.raw_ok:
        return {"candidate": candidate, "timings_ms": timings, "checks": checks,
                "outcome": "escalate", "reason": "llm_format"}
    return {"candidate": candidate, "timings_ms": timings, "checks": checks}


def _relevant_sentence(question: str, chunk_text: str) -> str:
    q = set(bigrams(question))
    best, best_score = "", -1
    for sentence in chunk_text.replace("\n", "。").split("。"):
        score = len(q & set(bigrams(sentence)))
        if score > best_score:
            best, best_score = sentence, score
    return best


def detect_conflict(question: str, items: list[RetrievedChunk]) -> dict[str, Any] | None:
    """跨文件數值衝突：各文件與問題最相關的句子中，同單位數值不同即視為衝突。

    Args:
        question: 遮罩後問題。
        items: 強相關證據（不同文件）。

    Returns:
        衝突描述；無衝突回傳 None。
    """
    by_doc: dict[uuid.UUID, tuple[RetrievedChunk, set[tuple[int, str]]]] = {}
    for item in items:
        if item.document_id in by_doc:
            continue
        by_doc[item.document_id] = (item, extract_quantities(_relevant_sentence(question, item.text)))
    docs = list(by_doc.values())
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            (a, qa), (b, qb) = docs[i], docs[j]
            units = {u for _, u in qa} & {u for _, u in qb}
            for unit in units:
                va = {v for v, u in qa if u == unit}
                vb = {v for v, u in qb if u == unit}
                if va.isdisjoint(vb):
                    return {"unit": unit, "a": {"chunk_id": str(a.chunk_id), "values": sorted(va)},
                            "b": {"chunk_id": str(b.chunk_id), "values": sorted(vb)}}
    return None


def node_verify(state: QaState) -> QaState:
    """驗證：引用存在、字面支持、輸出風險、跨文件衝突；LLM 自報只能多轉人工。"""
    policy: QaPolicy = state["policy"]
    candidate: CandidateAnswer = state["candidate"]
    evidence_map = state["evidence_map"]
    checks = dict(state.get("checks", {}))
    checks["llm_flags"] = {"needs_human": candidate.needs_human, "conflict": candidate.conflict,
                           "reason": candidate.reason}

    if candidate.conflict:
        return {"checks": checks, "outcome": "escalate", "reason": "conflict", "reason_detail": candidate.reason}
    if candidate.needs_human or not candidate.claims:
        reason = "suspicious_content" if "可疑指令" in candidate.reason else "insufficient"
        return {"checks": checks, "outcome": "escalate", "reason": reason, "reason_detail": candidate.reason}

    claim_checks, verified_claims = [], []
    for claim in candidate.claims:
        refs = [r for r in claim["citation_refs"] if r in evidence_map]
        unknown = [r for r in claim["citation_refs"] if r not in evidence_map]
        support = max(
            (
                support_score(
                    claim["text"],
                    f"{evidence_map[r].title}\n{evidence_map[r].locator}\n{evidence_map[r].text}",
                )
                for r in refs
            ),
            default=0.0,
        )

        claim_check = {
            "refs": refs,
            "unknown_refs": unknown,
            "support": round(support, 3),
        }

        if not refs or unknown:
            claim_check["accepted"] = False
            claim_check["reject_reason"] = "citation_missing"
            claim_checks.append(claim_check)
            checks["claims"] = claim_checks
            return {"checks": checks, "outcome": "escalate", "reason": "citation_missing"}

        if screen_risk(claim["text"], policy):
            claim_check["accepted"] = False
            claim_check["reject_reason"] = "output_risk"
            claim_checks.append(claim_check)
            checks["claims"] = claim_checks
            return {"checks": checks, "outcome": "escalate", "reason": "output_risk"}

        role_check = check_roles(claim['text'], [evidence_map[r].text for r in refs])
        claim_check['roles'] = role_check
        if not role_check['passed']:
            claim_check['accepted'] = False
            claim_check['reject_reason'] = 'role_mismatch'
            claim_checks.append(claim_check)
            checks['claims'] = claim_checks
            return {'checks': checks, 'outcome': 'escalate', 'reason': 'unsupported_claim',
                    'reason_detail': '引用正文的規範主體與回答角色不一致'}

        if support < policy.min_support:
            claim_check["accepted"] = False
            claim_check["reject_reason"] = "unsupported_claim"
            claim_checks.append(claim_check)
            continue

        claim_check["accepted"] = True
        claim_checks.append(claim_check)
        verified_claims.append({
            "text": claim["text"],
            "refs": refs,
            "support": round(support, 3),
        })

    checks["claims"] = claim_checks

    if not verified_claims:
        return {
            "checks": checks,
            "outcome": "escalate",
            "reason": "unsupported_claim",
        }

    if asks_penalty_amount(state["question_masked"]):
        responsive = any(
            answers_supported_penalty_amount(state["question_masked"], claim["text"], evidence_map[ref].text)
            for claim in verified_claims for ref in claim["refs"]
        )
        checks["answer_sufficiency"] = {"required_fact": "penalty_amount", "answered": responsive}
        if not responsive:
            return {"checks": checks, "outcome": "escalate", "reason": "insufficient",
                    "reason_detail": "回答未以引用證據提供所問的罰款或扣款金額"}

    if requested_field(state['question_masked']) in ('duration', 'frequency', 'quantity'):
        responsive = any(answers_requested_value(state['question_masked'], c['text'],
                         [evidence_map[r].text for r in c['refs']]) for c in verified_claims)
        checks['requested_fact_verification'] = {'field': requested_field(state['question_masked']), 'answered': responsive}
        if not responsive:
            return {'checks': checks, 'outcome': 'escalate', 'reason': 'insufficient',
                    'reason_detail': '回答未以引用證據提供問題所需的數值或期限'}

    strong = [item for item in evidence_map.values() if item.coverage >= policy.min_top_coverage
              or assess_evidence(state['question_masked'], item, policy).admitted]
    conflict = detect_conflict(state["question_masked"], strong)
    if conflict:
        checks["conflict"] = conflict
        return {"checks": checks, "outcome": "escalate", "reason": "conflict"}
    return {"checks": checks, "outcome": "answer", "claims": verified_claims}


def _route_after(state: QaState, next_node: str) -> str:
    return "end" if state.get("outcome") in {"escalate", "clarify"} else next_node


def build_graph() -> Any:
    """建立並編譯問答 StateGraph。"""
    graph = StateGraph(QaState)
    graph.add_node("deidentify", node_deidentify)
    graph.add_node("clarify", node_clarify)
    graph.add_node("screen_risk", node_screen_risk)
    graph.add_node("retrieve", node_retrieve)
    graph.add_node("generate", node_generate)
    graph.add_node("verify", node_verify)
    graph.add_edge(START, "deidentify")
    graph.add_edge("deidentify", "screen_risk")
    graph.add_conditional_edges("screen_risk", lambda s: _route_after(s, "clarify"),
                                {"clarify": "clarify", "end": END})
    graph.add_conditional_edges("clarify", lambda s: _route_after(s, "retrieve"),
                                {"retrieve": "retrieve", "end": END})
    graph.add_conditional_edges("retrieve", lambda s: _route_after(s, "generate"),
                                {"generate": "generate", "end": END})
    graph.add_conditional_edges("generate", lambda s: _route_after(s, "verify"),
                                {"verify": "verify", "end": END})
    graph.add_edge("verify", END)
    return graph.compile()


_GRAPH = None


def run_graph(initial: QaState) -> QaState:
    """執行問答流程。

    Args:
        initial: 初始狀態（須含 session、org_id、facility_type、today、question_raw）。

    Returns:
        最終狀態。
    """
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    initial.setdefault("policy", DEFAULT_POLICY)
    initial.setdefault("timings_ms", {})
    start = time.perf_counter()
    final: QaState = _GRAPH.invoke(initial)
    final["timings_ms"] = dict(final.get("timings_ms", {}), graph_total=_ms(start))
    return final


