"""把 ORM 物件轉成 API 回應。所有出處連結都由後端依 metadata 產生。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Case,
    CaseEvent,
    CaseMessage,
    Category,
    Chunk,
    Citation,
    Document,
    DocumentVersion,
    Feedback,
    QaItem,
    Transcript,
    TranscriptSegment,
    TtsAsset,
    User,
)
from app.services import documents as doc_service
from app.services import transcripts as tr_service
from app.services.cases import SOURCE_LABELS, STATUS_LABELS
from app.services.qa_graph import REASON_TEXT
from app.services.tts_service import media_url

AI_LABEL = "AI 初步參考"


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def case_brief(case: Case | None) -> dict[str, Any] | None:
    """案件摘要。"""
    if case is None:
        return None
    return {"id": str(case.id), "number": case.number, "status": case.status,
            "status_label": STATUS_LABELS[case.status]}


def citations_out(db: Session, qa_item_id: Any) -> list[dict[str, Any]]:
    """問答的出處卡。"""
    rows = db.execute(
        select(Citation, Chunk, DocumentVersion, Document)
        .join(Chunk, Chunk.id == Citation.chunk_id)
        .join(DocumentVersion, DocumentVersion.id == Citation.version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Citation.qa_item_id == qa_item_id)
        .order_by(Citation.rank)
    ).all()
    out = []
    for citation, chunk, version, document in rows:
        excerpt = chunk.text if len(chunk.text) <= 160 else chunk.text[:160] + "…"
        out.append({
            "id": citation.label,
            "chunk_id": str(chunk.id),
            "version_id": str(version.id),
            "document_title": document.title,
            "doc_type": document.doc_type,
            "locator": chunk.locator,
            "version_label": version.version_label,
            "effective_from": _iso(version.effective_from),
            "effective_to": _iso(version.effective_to),
            "version_status": version.status,
            "source": version.source,
            "source_url": f"/api/sources/chunks/{chunk.id}",
            "external_url": version.source_url,
            "excerpt": excerpt,
        })
    return out


def qa_out(db: Session, item: QaItem, case: Case | None = None) -> dict[str, Any]:
    """問答回應（AnswerOut）。不含相似度、信心分數或正確率。"""
    if case is None and item.outcome in {"escalated"}:
        case = db.scalar(select(Case).where(Case.qa_item_id == item.id).order_by(Case.created_at))
    manual_case = db.scalar(
        select(Case).where(Case.qa_item_id == item.id, Case.source == "manual_escalation").order_by(Case.created_at)
    )
    tts = db.scalar(select(TtsAsset).where(TtsAsset.qa_item_id == item.id))
    wrong = db.scalar(select(Feedback.id).where(Feedback.qa_item_id == item.id, Feedback.kind == "wrong"))
    settings = get_settings()
    return {
        "id": str(item.id),
        "created_at": _iso(item.created_at),
        "outcome": item.outcome,
        "label": AI_LABEL,
        "question_masked": item.question_masked,
        "answer_text": item.answer_text,
        "claims": item.claims,
        "safety_notice": item.checks.get("ba16_safety_note") if item.outcome == "answered" else None,
        "citations": citations_out(db, item.id) if item.outcome == "answered" else [],
        "escalation_reason": item.escalation_reason,
        "escalation_reason_text": REASON_TEXT.get(item.escalation_reason or "") if item.escalation_reason else None,
        "case": case_brief(case),
        "manual_case": case_brief(manual_case),
        "case_error": item.case_error,
        "feedback_wrong": wrong is not None,
        "tts": {"status": tts.status, "audio_url": media_url(tts), "error": tts.error} if tts else None,
        "modes": {"llm": item.llm_provider, "embedding": item.embedding_provider, "line": settings.line_mode},
        "qa_policy_version": item.qa_policy_version,
        "wake_word": bool((item.checks or {}).get("wake_word")),
    }


def case_out(db: Session, case: Case, *, include_internal: bool) -> dict[str, Any]:
    """案件詳情。include_internal=True（督導）時附 AI 引用與歷程。"""
    category = db.get(Category, case.category_id) if case.category_id else None
    creator = db.get(User, case.created_by)
    assignee = db.get(User, case.assignee_id) if case.assignee_id else None
    messages = db.scalars(select(CaseMessage).where(CaseMessage.case_id == case.id).order_by(CaseMessage.created_at))
    data: dict[str, Any] = {
        "id": str(case.id),
        "number": case.number,
        "status": case.status,
        "status_label": STATUS_LABELS[case.status],
        "source": case.source,
        "source_label": SOURCE_LABELS.get(case.source, case.source),
        "category": {"id": str(category.id), "name": category.name} if category else None,
        "summary_masked": case.summary_masked,
        "reason": case.reason,
        "created_at": _iso(case.created_at),
        "updated_at": _iso(case.updated_at),
        "first_replied_at": _iso(case.first_replied_at),
        "closed_at": _iso(case.closed_at),
        "creator": {"id": str(creator.id), "display_name": creator.display_name} if creator else None,
        "assignee": {"id": str(assignee.id), "display_name": assignee.display_name} if assignee else None,
        "messages": [
            {"id": str(m.id), "author_role": m.author_role, "body": m.body, "created_at": _iso(m.created_at),
             "author_name": (db.get(User, m.author_id).display_name if db.get(User, m.author_id) else "")}
            for m in messages
        ],
        "qa_item_id": str(case.qa_item_id) if case.qa_item_id else None,
        "transcript_id": str(case.transcript_id) if case.transcript_id else None,
    }
    if include_internal:
        from app.models import NotificationJob

        qa = db.get(QaItem, case.qa_item_id) if case.qa_item_id else None
        data["qa"] = qa_out(db, qa) if qa else None
        data["retrieval_refs"] = _retrieval_refs(db, qa) if qa and qa.outcome != "answered" else []
        data["events"] = [
            {"kind": e.kind, "from_status": e.from_status, "to_status": e.to_status, "data": e.data,
             "created_at": _iso(e.created_at),
             "actor": (db.get(User, e.actor_id).display_name if e.actor_id and db.get(User, e.actor_id) else "系統")}
            for e in db.scalars(select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.id))
        ]
        data["notifications"] = [
            {"id": str(n.id), "status": n.status, "attempts": n.attempts, "last_error_code": n.last_error_code,
             "accepted_at": _iso(n.accepted_at), "created_at": _iso(n.created_at)}
            for n in db.scalars(select(NotificationJob).where(NotificationJob.case_id == case.id)
                                .order_by(NotificationJob.created_at))
        ]
        if case.transcript_id:
            data["transcript"] = transcript_out(db, db.get(Transcript, case.transcript_id), include_draft=False)
    return data


def _retrieval_refs(db: Session, qa: QaItem) -> list[dict[str, Any]]:
    """轉人工案件：列出檢索到但未被採用的候選條文，供督導參考（非回答）。"""
    refs = []
    for entry in (qa.checks or {}).get("retrieval", [])[:4]:
        chunk = db.get(Chunk, entry["chunk_id"])
        if chunk is None:
            continue
        version = db.get(DocumentVersion, chunk.version_id)
        document = db.get(Document, version.document_id) if version else None
        refs.append({"chunk_id": str(chunk.id), "document_title": document.title if document else "",
                     "locator": chunk.locator, "version_label": version.version_label if version else "",
                     "source_url": f"/api/sources/chunks/{chunk.id}",
                     "injection_flag": entry.get("injection_flag", False)})
    return refs


def transcript_out(db: Session, transcript: Transcript | None, *, include_draft: bool) -> dict[str, Any] | None:
    """轉錄狀態與內容。草稿（未遮罩）只在 include_draft=True（本人）時回傳。"""
    if transcript is None:
        return None
    data: dict[str, Any] = {
        "id": str(transcript.id),
        "status": transcript.status,
        "mode": transcript.mode,
        "channel": transcript.channel,
        "audio_duration_ms": transcript.audio_duration_ms,
        "error_code": transcript.error_code,
        "error_message": transcript.error_message,
        "uploaded_at": _iso(transcript.uploaded_at),
        "draft_expires_at": _iso(transcript.draft_expires_at),
        "audio_deleted": transcript.audio_deleted_at is not None,
        "roles": transcript.speaker_roles or {},
        "summary_masked": transcript.summary_masked,
        "stt_provider": transcript.stt_provider,
        "stt_ms": transcript.stt_ms,
        "segments": [],
    }
    if transcript.status == "draft" and include_draft:
        data["segments"] = [dict(s, masked=False) for s in tr_service.read_draft(transcript)]
    elif transcript.status == "confirmed":
        data["segments"] = [
            {"idx": s.idx, "start_ms": s.start_ms, "end_ms": s.end_ms, "speaker": s.speaker,
             "text": s.text_masked, "uncertain": s.uncertain, "edited": s.edited, "selected": s.selected,
             "masked": True}
            for s in db.scalars(select(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript.id)
                                .order_by(TranscriptSegment.idx))
        ]
    return data


def version_out(db: Session, version: DocumentVersion, *, with_chunks: bool = False) -> dict[str, Any]:
    """文件版本。"""
    data = {
        "id": str(version.id),
        "document_id": str(version.document_id),
        "version_label": version.version_label,
        "status": version.status,
        "effective_from": _iso(version.effective_from),
        "effective_to": _iso(version.effective_to),
        "source": version.source,
        "source_url": version.source_url,
        "file_name": version.file_name,
        "mime": version.mime,
        "page_count": version.page_count,
        "chunk_count": version.chunk_count,
        "warnings": version.warnings or [],
        "parse_error": version.parse_error,
        "missing_fields": doc_service.missing_fields(version),
        "uploaded_at": _iso(version.uploaded_at),
        "published_at": _iso(version.published_at),
        "deactivated_at": _iso(version.deactivated_at),
    }
    if with_chunks:
        data["chunks"] = [
            {"id": str(c.id), "seq": c.seq, "locator": c.locator, "text": c.text}
            for c in db.scalars(select(Chunk).where(Chunk.version_id == version.id).order_by(Chunk.seq))
        ]
    return data
