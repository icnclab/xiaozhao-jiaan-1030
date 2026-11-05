"""問答服務：執行 StateGraph、在同一交易保存問答與引用，轉人工時建案。

建案失敗時 outcome 為 `escalation_failed`、不回傳案件，前端據此顯示真實狀態與重試，
絕不先承諾「已送交」。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Case, Citation, DeidTerm, Organization, QaItem, User
from app.providers.llm import get_llm_provider
from app.services import audit, cases
from app.services.qa_graph import REASON_TEXT, run_graph
from app.services.qa_policy import DEFAULT_POLICY
from app.services.wake import greeting_reply, strip_wake_word

MAX_QUESTION_CHARS = 500
EMERGENCY_NOTE = "如為緊急狀況，請立即依機構緊急應變程序處理，並通知在場護理人員。"


class QaError(Exception):
    """問答輸入錯誤。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def load_deid_terms(session: Session, org_id: uuid.UUID) -> set[tuple[str, int]]:
    """載入機構自訂遮罩詞（HMAC）。"""
    rows = session.execute(select(DeidTerm.term_hmac, DeidTerm.length).where(DeidTerm.org_id == org_id)).all()
    return {(row.term_hmac, row.length) for row in rows}


def _today() -> datetime:
    return datetime.now(ZoneInfo(get_settings().tz_name))


def auto_case_request_id(qa_item_id: uuid.UUID) -> str:
    """AI 轉人工建案的冪等鍵（重試建案不會產生第二個案件）。"""
    return f"auto:{qa_item_id}"


def ask(
    session: Session,
    user: User,
    *,
    question: str,
    source: str,
    client_request_id: str,
    transcript_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
) -> tuple[QaItem, Case | None, bool]:
    """回答問題或轉人工。

    Args:
        session: ORM session（本函式會 commit）。
        user: 已驗證的使用者。
        question: 使用者輸入的原始問題（可能含個資；只在記憶體處理）。
        source: text、voice、transcript、line_text、line_voice。
        client_request_id: 冪等鍵。
        transcript_id: 關聯轉錄。
        category_id: 關聯分類。
        conversation_id: 同一查詢脈絡 ID。

    Returns:
        (問答, 案件或 None, 是否新建)。

    Raises:
        QaError: 輸入不合法。
    """
    existing = session.scalar(
        select(QaItem).where(QaItem.user_id == user.id, QaItem.client_request_id == client_request_id)
    )
    if existing:
        case = session.scalar(select(Case).where(Case.qa_item_id == existing.id).order_by(Case.created_at))
        return existing, case, False

    wake = strip_wake_word(question)
    if wake.greeting_only:
        raise QaError("greeting_only", greeting_reply())
    question = wake.text
    if not question:
        raise QaError("empty", "請輸入問題")
    if len(question) > MAX_QUESTION_CHARS:
        raise QaError("too_long", f"問題請在 {MAX_QUESTION_CHARS} 字以內")

    from app.services.query_understanding import contextual_question
    previous = None
    if conversation_id:
        previous = session.scalar(select(QaItem.question_masked).where(
            QaItem.user_id == user.id, QaItem.org_id == user.org_id,
            QaItem.conversation_id == conversation_id,
        ).order_by(QaItem.created_at.desc()).limit(1))
    question = contextual_question(question, previous)

    org = session.get(Organization, user.org_id)
    assert org is not None
    today = _today().date()
    state = run_graph(
        {
            "session": session,
            "org_id": org.id,
            "facility_type": org.facility_type,
            "today": today,
            "question_raw": question,
            "deid_terms": load_deid_terms(session, org.id),
            "policy": DEFAULT_POLICY,
        }
    )
    provider = get_llm_provider()
    settings = get_settings()
    from app.services.quality_trace import capture as capture_quality_trace
    try:
        quality_trace = capture_quality_trace(state)
    except Exception as exc:
        # Observability failures must not change an existing answer/risk decision.
        quality_trace = {"unavailable": ["runtime_trace"], "capture_error": type(exc).__name__}
    item = QaItem(
        org_id=org.id,
        user_id=user.id,
        conversation_id=conversation_id or uuid.uuid4(),
        client_request_id=client_request_id,
        source=source,
        transcript_id=transcript_id,
        category_id=category_id,
        question_masked=state["question_masked"],
        outcome=("answered" if state.get("outcome") == "answer" else "clarify" if state.get("outcome") == "clarify" else "escalated"),
        checks=dict(state.get("checks", {}), wake_word=wake.matched, rag_trace=quality_trace),
        llm_provider=provider.name,
        llm_model=provider.model,
        embedding_provider=settings.embedding_provider,
        qa_policy_version=DEFAULT_POLICY.version,
        timings_ms=state.get("timings_ms", {}),
    )
    session.add(item)
    session.flush()

    case: Case | None = None
    if item.outcome == "answered":
        evidence_map = state["evidence_map"]
        ref_to_label: dict[str, str] = {}
        stored_claims = []
        # Public citations correspond to the displayed, verified claims.
        from app.services.answer_presentation import assemble_answer
        display_claims, safety_note = assemble_answer(item.question_masked, evidence_map, state["claims"])
        for claim in display_claims:
            for ref in claim["refs"]:
                if ref not in ref_to_label:
                    ref_to_label[ref] = f"c{len(ref_to_label) + 1}"
        for claim in display_claims:
            labels = [ref_to_label[ref] for ref in claim['refs']]
            stored_claims.append({"text": claim["text"], "citations": labels, "support": claim["support"]})
        for rank, (ref, label) in enumerate(ref_to_label.items(), start=1):
            chunk = evidence_map[ref]
            support = max(
                (c["support"] for c in state["claims"] if ref in c["refs"]), default=None
            )
            session.add(Citation(qa_item_id=item.id, chunk_id=chunk.chunk_id, version_id=chunk.version_id,
                                 label=label, rank=rank, support_score=support))
        item.claims = stored_claims
        item.answer_text = "\n".join(
            f"{c['text'].rstrip('。')}（出處 {'、'.join(x[1:] for x in c['citations'])}）。" for c in stored_claims
        )
        if safety_note:
            item.checks = dict(item.checks, ba16_safety_note=safety_note.strip())
            item.answer_text += safety_note
    elif item.outcome == "clarify":
        item.escalation_reason = None
        item.escalation_detail = None
        item.answer_text = state.get('checks', {}).get('clarification', {}).get('prompt') or "可以再說具體一點嗎？例如發生了什麼事、要做什麼，或你想確認哪一項規定。"
        case = None
    else:
        reason_code = state.get("reason") or "insufficient"
        item.escalation_reason = reason_code
        item.escalation_detail = (state.get("reason_detail") or "")[:300] or None
        from app.services.public_messages import escalation_message
        from app.services.jiaan1030_role_guard import make_role_aware
        item.answer_text = make_role_aware(reason_code, user.role, escalation_message(reason_code), question=item.question_masked)
        case = try_create_escalation_case(session, user, item)

    audit.record(
        session, "qa.ask", actor=user, target_type="qa_item", target_id=item.id,
        meta={"outcome": item.outcome, "reason": item.escalation_reason, "source": source,
              "deid_hits": sum(state.get("deid_hits", {}).values()), "policy": DEFAULT_POLICY.version},
    )
    session.commit()
    return item, case, True


def try_create_escalation_case(session: Session, user: User, item: QaItem) -> Case | None:
    """為 AI 轉人工建案；失敗時把問答標為 escalation_failed 並記錄原因。"""
    try:
        case, _ = cases.create_case(
            session, user, source="ai_escalation", summary_masked=item.question_masked,
            reason=REASON_TEXT.get(item.escalation_reason or "", "AI 轉人工"),
            client_request_id=auto_case_request_id(item.id), category_id=item.category_id,
            qa_item_id=item.id, transcript_id=item.transcript_id,
        )
    except Exception as exc:  # 建案失敗要照實呈現
        item.outcome = "escalation_failed"
        item.case_error = f"建立督導案件失敗（{type(exc).__name__}），請按「重試送交」"
        audit.record(session, "case.create", actor=user, target_type="qa_item", target_id=item.id,
                     outcome="error", meta={"error": type(exc).__name__})
        return None
    item.outcome = "escalated"
    item.case_error = None
    return case


def manual_escalate(session: Session, user: User, item: QaItem, note: str, client_request_id: str) -> Case:
    """照服員手動「送交督導確認」。

    Raises:
        cases.CaseError: 建案失敗（由 API 回報真實狀態）。
    """
    from app.services.deid import deidentify

    summary = item.question_masked
    note_masked = deidentify(note.strip()).text if note else ""
    if note_masked:
        summary += f"\n照服員補充：{note_masked}"
    reason = "照服員對 AI 回答仍有疑慮" if item.outcome == "answered" else "照服員送交確認"
    case, _ = cases.create_case(
        session, user, source="manual_escalation", summary_masked=summary, reason=reason,
        client_request_id=client_request_id, category_id=item.category_id, qa_item_id=item.id,
        transcript_id=item.transcript_id,
    )
    session.commit()
    return case


def retry_escalation(session: Session, user: User, item: QaItem) -> Case | None:
    """重試 escalation_failed 的建案（冪等）。"""
    if item.outcome != "escalation_failed":
        return session.scalar(select(Case).where(Case.qa_item_id == item.id).order_by(Case.created_at))
    case = try_create_escalation_case(session, user, item)
    session.commit()
    return case
