"""照服員端 API：問答、語音與轉錄、分類回報、我的案件、出處入口、語音播放。"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.serializers import case_out, qa_out, transcript_out
from app.auth import current_user, deny_not_found, require_roles
from app.config import get_settings
from app.db import get_db
from app.models import (
    Case,
    Category,
    CategoryTemplate,
    Chunk,
    Document,
    DocumentVersion,
    Feedback,
    Organization,
    QaItem,
    Transcript,
    TtsAsset,
    User,
)
from app.security import verify_media_token
from app.services import audit, cases, qa_service, source_downloads, transcripts, tts_service
from app.services.deid import deidentify
from app.services.documents import current_versions
from app.services.source_access import visible_version

router = APIRouter()
ANY_ROLE = ("caregiver", "supervisor", "admin")


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _parse_uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise _err(404, "not_found", "找不到資料") from exc


def _own_qa(db: Session, user: User, qa_id: str) -> QaItem:
    item = db.get(QaItem, _parse_uuid(qa_id))
    if item is None:
        raise _err(404, "not_found", "找不到資料")
    allowed = item.user_id == user.id or (user.role in {"supervisor", "admin"} and item.org_id == user.org_id)
    if not allowed:
        raise deny_not_found(db, user, "qa_item", qa_id)
    return item


def _own_transcript(db: Session, user: User, transcript_id: str) -> Transcript:
    transcript = db.get(Transcript, _parse_uuid(transcript_id))
    if transcript is None:
        raise _err(404, "not_found", "找不到資料")
    if transcript.user_id != user.id:
        raise deny_not_found(db, user, "transcript", transcript_id)
    return transcript


# ── 問答 ─────────────────────────────────────────────────────────────


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    source: str = Field(default="text", pattern="^(text|voice|transcript)$")
    transcript_id: str | None = None
    category_id: str | None = None
    conversation_id: str | None = None
    client_request_id: str = Field(min_length=8, max_length=64)


@router.post("/qa/ask")
def ask(body: AskIn, user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    """提問：附出處回答或轉督導（見 docs/api-contract.md §2）。"""
    transcript_id = None
    if body.transcript_id:
        transcript = _own_transcript(db, user, body.transcript_id)
        if transcript.status != "confirmed":
            raise _err(409, "transcript_not_confirmed", "請先確認轉錄內容")
        transcript_id = transcript.id
    category_id = None
    if body.category_id:
        category = db.get(Category, _parse_uuid(body.category_id))
        if category is None or category.org_id != user.org_id:
            raise deny_not_found(db, user, "category", body.category_id)
        category_id = category.id
    try:
        item, case, _ = qa_service.ask(
            db, user, question=body.question, source=body.source, client_request_id=body.client_request_id,
            transcript_id=transcript_id, category_id=category_id,
            conversation_id=_parse_uuid(body.conversation_id) if body.conversation_id else None,
        )
    except qa_service.QaError as exc:
        raise _err(422, exc.code, str(exc)) from exc
    return qa_out(db, item, case)


@router.get("/qa/history")
def qa_history(user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> list[dict]:
    """自己的問答（最新 50 筆）。"""
    items = db.scalars(select(QaItem).where(QaItem.user_id == user.id).order_by(QaItem.created_at.desc()).limit(50))
    return [{"id": str(i.id), "created_at": i.created_at.isoformat(), "question_masked": i.question_masked,
             "outcome": i.outcome} for i in items]


@router.get("/qa/{qa_id}")
def qa_detail(qa_id: str, user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    """單筆問答。"""
    return qa_out(db, _own_qa(db, user, qa_id))


class EscalateIn(BaseModel):
    note: str = Field(default="", max_length=500)
    client_request_id: str = Field(min_length=8, max_length=64)


@router.post("/qa/{qa_id}/escalate")
def escalate(qa_id: str, body: EscalateIn, user: User = Depends(require_roles(*ANY_ROLE)),
             db: Session = Depends(get_db)) -> dict:
    """手動送交督導確認；建案失敗回 503 與可重試，不回傳假案件。"""
    item = _own_qa(db, user, qa_id)
    if item.user_id != user.id:
        raise _err(403, "forbidden", "只能送交自己的提問")
    try:
        case = qa_service.manual_escalate(db, user, item, body.note, body.client_request_id)
    except cases.CaseError as exc:
        raise _err(400, exc.code, str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail={"code": "case_create_failed", "retryable": True,
                                                     "message": f"送交失敗（{type(exc).__name__}），尚未轉交督導，請重試"}) from exc
    return {"case": {"id": str(case.id), "number": case.number, "status": case.status}}


@router.post("/qa/{qa_id}/retry-escalation")
def retry_escalation(qa_id: str, user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    """重試 escalation_failed 的建案。"""
    item = _own_qa(db, user, qa_id)
    qa_service.retry_escalation(db, user, item)
    return qa_out(db, item)


class FeedbackIn(BaseModel):
    kind: str = Field(pattern="^(wrong|helpful)$")
    reason: str = Field(default="", max_length=300)


@router.post("/qa/{qa_id}/feedback")
def feedback(qa_id: str, body: FeedbackIn, user: User = Depends(require_roles(*ANY_ROLE)),
             db: Session = Depends(get_db)) -> dict:
    """回答回饋（同一人同一種回饋只記一次）。"""
    item = _own_qa(db, user, qa_id)
    existing = db.scalar(select(Feedback).where(Feedback.qa_item_id == item.id, Feedback.user_id == user.id,
                                                Feedback.kind == body.kind))
    if existing is None:
        db.add(Feedback(org_id=user.org_id, qa_item_id=item.id, user_id=user.id, kind=body.kind,
                        reason_masked=deidentify(body.reason).text if body.reason else None))
        audit.record(db, "qa.feedback", actor=user, target_type="qa_item", target_id=item.id,
                     meta={"kind": body.kind})
        db.commit()
    return {"ok": True}


@router.post("/qa/{qa_id}/tts")
def request_tts(qa_id: str, user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    """點選播放：建立語音工作（冪等）。"""
    item = _own_qa(db, user, qa_id)
    if not item.answer_text:
        raise _err(409, "no_text", "沒有可朗讀的內容")
    asset = tts_service.request_tts(db, user, item)
    return {"status": asset.status, "audio_url": tts_service.media_url(asset), "error": asset.error}


@router.get("/qa/{qa_id}/tts")
def tts_status(qa_id: str, user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    """語音工作狀態。"""
    item = _own_qa(db, user, qa_id)
    asset = db.scalar(select(TtsAsset).where(TtsAsset.qa_item_id == item.id))
    if asset is None:
        return {"status": "none", "audio_url": None, "error": None}
    return {"status": asset.status, "audio_url": tts_service.media_url(asset), "error": asset.error}


@router.get("/media/tts/{token}")
def media_tts(token: str, db: Session = Depends(get_db)) -> FileResponse:
    """限時簽章的語音檔（無需 Bearer，供 LINE 音訊訊息使用）。"""
    token_id = verify_media_token(token)
    if token_id is None:
        raise _err(404, "not_found", "連結無效或已過期")
    asset = db.scalar(select(TtsAsset).where(TtsAsset.token_id == token_id))
    if asset is None or asset.status != "ready" or not asset.file_path or not Path(asset.file_path).exists():
        raise _err(404, "not_found", "連結無效或已過期")
    return FileResponse(asset.file_path, media_type="audio/mp4",
                        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


# ── 語音與轉錄 ────────────────────────────────────────────────────────


@router.post("/audio/uploads")
async def upload_audio(
    file: UploadFile = File(...),
    mode: str = Form(...),
    client_upload_id: str = Form(..., min_length=8, max_length=64),
    consent_confirmed: bool = Form(False),
    user: User = Depends(require_roles(*ANY_ROLE)),
    db: Session = Depends(get_db),
) -> dict:
    """上傳錄音（停止錄音後自動呼叫）。格式以實際解碼驗證。"""
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise _err(413, "too_large", f"音訊超過 {get_settings().max_upload_mb} MB")
    try:
        transcript, created = transcripts.create_upload(
            db, user, data=data, mode=mode, client_upload_id=client_upload_id,
            consent_confirmed=consent_confirmed, client_mime=file.content_type,
        )
    except transcripts.TranscriptError as exc:
        raise _err(exc.http_status, exc.code, str(exc)) from exc
    return {"transcript_id": str(transcript.id), "status": transcript.status, "created": created}


@router.get("/transcripts")
def list_transcripts(user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> list[dict]:
    """我的錄音／轉錄紀錄（最新 30 筆，不含草稿內容）。"""
    rows = db.scalars(select(Transcript).where(Transcript.user_id == user.id)
                      .order_by(Transcript.uploaded_at.desc()).limit(30))
    out = []
    for t in rows:
        data = transcript_out(db, t, include_draft=False) or {}
        data["segments"] = []
        out.append(data)
    return out


@router.get("/transcripts/{transcript_id}")
def get_transcript(transcript_id: str, user: User = Depends(require_roles(*ANY_ROLE)),
                   db: Session = Depends(get_db)) -> dict:
    """轉錄狀態與內容（草稿只給本人）。"""
    return transcript_out(db, _own_transcript(db, user, transcript_id), include_draft=True) or {}


class SegmentEdit(BaseModel):
    idx: int
    text: str | None = Field(default=None, max_length=2000)
    speaker: str | None = Field(default=None, max_length=20)
    uncertain: bool | None = None


class ConfirmIn(BaseModel):
    segments: list[SegmentEdit] = Field(default_factory=list)
    roles: dict[str, str] = Field(default_factory=dict)
    selected_idx: list[int] = Field(default_factory=list)
    summary: str | None = Field(default=None, max_length=1000)


@router.post("/transcripts/{transcript_id}/confirm")
def confirm_transcript(transcript_id: str, body: ConfirmIn, user: User = Depends(require_roles(*ANY_ROLE)),
                       db: Session = Depends(get_db)) -> dict:
    """確認轉錄：保存遮罩版與修訂軌跡，刪除未遮罩草稿。"""
    transcript = _own_transcript(db, user, transcript_id)
    edits = [{k: v for k, v in e.model_dump().items() if v is not None} for e in body.segments]
    try:
        transcripts.confirm(db, user, transcript, edits=edits, roles=body.roles, selected_idx=body.selected_idx,
                            summary=body.summary)
    except transcripts.TranscriptError as exc:
        raise _err(exc.http_status, exc.code, str(exc)) from exc
    return transcript_out(db, transcript, include_draft=False) or {}


@router.post("/transcripts/{transcript_id}/retry")
def retry_transcript(transcript_id: str, user: User = Depends(require_roles(*ANY_ROLE)),
                     db: Session = Depends(get_db)) -> dict:
    """失敗重試；音訊已清除回 410。"""
    transcript = _own_transcript(db, user, transcript_id)
    try:
        transcripts.retry(db, user, transcript)
    except transcripts.TranscriptError as exc:
        raise _err(exc.http_status, exc.code, str(exc)) from exc
    return transcript_out(db, transcript, include_draft=True) or {}


@router.delete("/transcripts/{transcript_id}", status_code=204)
def cancel_transcript(transcript_id: str, user: User = Depends(require_roles(*ANY_ROLE)),
                      db: Session = Depends(get_db)) -> None:
    """取消並立即清除音訊與草稿。"""
    transcripts.cancel(db, user, _own_transcript(db, user, transcript_id))


# ── 分類與案件 ────────────────────────────────────────────────────────


@router.get("/categories")
def list_categories(user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> list[dict]:
    """啟用中的分類與模板（依機構）。"""
    categories = db.scalars(select(Category).where(Category.org_id == user.org_id, Category.is_active.is_(True))
                            .order_by(Category.sort_order, Category.name))
    out = []
    for category in categories:
        templates = db.scalars(select(CategoryTemplate).where(CategoryTemplate.category_id == category.id,
                                                              CategoryTemplate.is_active.is_(True))
                               .order_by(CategoryTemplate.sort_order))
        out.append({"id": str(category.id), "name": category.name, "description": category.description,
                    "templates": [{"id": str(t.id), "text": t.text} for t in templates]})
    return out


class CaseIn(BaseModel):
    category_id: str
    template_id: str | None = None
    text: str = Field(default="", max_length=1000)
    transcript_id: str | None = None
    answer_id: str | None = None
    client_request_id: str = Field(min_length=8, max_length=64)


@router.post("/cases")
def create_case(body: CaseIn, user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    """分類快速回報：分類→常見問題→補充→確認送出。建案成功才回傳案件。"""
    category = db.get(Category, _parse_uuid(body.category_id))
    if category is None or category.org_id != user.org_id or not category.is_active:
        raise deny_not_found(db, user, "category", body.category_id)
    parts = [f"【{category.name}】"]
    if body.template_id:
        template = db.get(CategoryTemplate, _parse_uuid(body.template_id))
        if template is None or template.category_id != category.id:
            raise _err(404, "not_found", "找不到常見問題模板")
        parts.append(template.text)
    if body.text.strip():
        parts.append(deidentify(body.text.strip()).text)
    transcript_id = None
    if body.transcript_id:
        transcript = _own_transcript(db, user, body.transcript_id)
        if transcript.status != "confirmed":
            raise _err(409, "transcript_not_confirmed", "請先確認轉錄內容")
        transcript_id = transcript.id
        if transcript.summary_masked:
            parts.append(f"談話摘要：{transcript.summary_masked}")
    qa_item_id = None
    if body.answer_id:
        qa_item_id = _own_qa(db, user, body.answer_id).id
    if len(parts) == 1:
        raise _err(422, "empty", "請選擇常見問題或補充說明")
    try:
        case, _ = cases.create_case(
            db, user, source="quick_report", summary_masked="\n".join(parts), reason="分類回報",
            client_request_id=body.client_request_id, category_id=category.id, qa_item_id=qa_item_id,
            transcript_id=transcript_id,
        )
        db.commit()
    except cases.CaseError as exc:
        raise _err(400, exc.code, str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail={"code": "case_create_failed", "retryable": True,
                                                     "message": "送交失敗，尚未轉交督導，請重試"}) from exc
    return case_out(db, case, include_internal=False)


@router.get("/cases/mine")
def my_cases(user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> list[dict]:
    """我的案件。"""
    rows = db.scalars(select(Case).where(Case.created_by == user.id).order_by(Case.updated_at.desc()).limit(100))
    return [{"id": str(c.id), "number": c.number, "status": c.status,
             "status_label": cases.STATUS_LABELS[c.status], "summary_masked": c.summary_masked[:80],
             "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat(),
             "has_reply": c.first_replied_at is not None} for c in rows]


def _visible_case(db: Session, user: User, case_id: str) -> Case:
    case = db.get(Case, _parse_uuid(case_id))
    if case is None:
        raise _err(404, "not_found", "找不到資料")
    if case.created_by != user.id and not (user.role in {"supervisor", "admin"} and case.org_id == user.org_id):
        raise deny_not_found(db, user, "case", case_id)
    return case


@router.get("/cases/{case_id}")
def case_detail(case_id: str, user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    """案件詳情（照服員看自己的；督導看同機構的）。"""
    case = _visible_case(db, user, case_id)
    return case_out(db, case, include_internal=user.role in {"supervisor", "admin"})


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
    client_request_id: str = Field(min_length=8, max_length=64)


@router.post("/cases/{case_id}/messages")
def add_message(case_id: str, body: MessageIn, user: User = Depends(require_roles(*ANY_ROLE)),
                db: Session = Depends(get_db)) -> dict:
    """照服員補充說明。"""
    case = _visible_case(db, user, case_id)
    try:
        cases.caregiver_message(db, user, case, body.body, body.client_request_id)
        db.commit()
    except cases.CaseError as exc:
        raise _err(400, exc.code, str(exc)) from exc
    return case_out(db, case, include_internal=False)


# ── 知識庫涵蓋範圍與出處入口 ──────────────────────────────────────────


@router.get("/documents/coverage")
def coverage(user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    """知識庫涵蓋範圍：現行文件、版本、生效日、更新時間。"""
    org = db.get(Organization, user.org_id)
    today = datetime.now(ZoneInfo(get_settings().tz_name)).date()
    version_ids = current_versions(db, org.id, org.facility_type, today)
    rows = db.execute(
        select(DocumentVersion, Document).join(Document, Document.id == DocumentVersion.document_id)
        .where(DocumentVersion.id.in_(version_ids)).order_by(Document.doc_type, Document.title)
    ).all() if version_ids else []
    last = max((v.published_at for v, _ in rows if v.published_at), default=None)
    return {
        "updated_at": last.isoformat() if last else None,
        "documents": [
            {"title": d.title, "doc_type": d.doc_type, "scope": "shared" if d.org_id is None else "org",
             "version_label": v.version_label, "effective_from": v.effective_from.isoformat() if v.effective_from else None,
             "effective_to": v.effective_to.isoformat() if v.effective_to else None, "chunk_count": v.chunk_count,
             "source": v.source}
            for v, d in rows
        ],
        "not_covered": ["醫療診斷與用藥建議", "補助或費用金額試算", "排班與人力調度", "知識庫未收錄的法規與內規"],
    }


def _visible_version(db: Session, user: User, version_id: uuid.UUID) -> tuple[DocumentVersion, Document]:
    return visible_version(db, user, version_id)


@router.get("/sources/chunks/{chunk_id}")
def source_chunk(chunk_id: str, user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    """出處原文入口：顯示當時引用版本的切塊全文與版本資訊（含已被新版取代的版本）。"""
    chunk = db.get(Chunk, _parse_uuid(chunk_id))
    if chunk is None:
        raise _err(404, "not_found", "找不到資料")
    version, document = _visible_version(db, user, chunk.version_id)
    neighbours = db.scalars(select(Chunk).where(Chunk.version_id == version.id,
                                                Chunk.seq.between(chunk.seq - 1, chunk.seq + 1)).order_by(Chunk.seq))
    audit.record(db, "source.view", actor=user, target_type="chunk", target_id=chunk.id)
    db.commit()
    return {
        "chunk": {"id": str(chunk.id), "locator": chunk.locator, "text": chunk.text, "page_no": chunk.page_no},
        "context": [{"id": str(c.id), "locator": c.locator, "text": c.text, "is_target": c.id == chunk.id}
                    for c in neighbours],
        "document": {"title": document.title, "doc_type": document.doc_type},
        "version": {"id": str(version.id), "version_label": version.version_label, "status": version.status,
                    "effective_from": version.effective_from.isoformat() if version.effective_from else None,
                    "effective_to": version.effective_to.isoformat() if version.effective_to else None,
                    "source": version.source, "source_url": version.source_url,
                    "file_url": f"/api/sources/versions/{version.id}/file"},
    }


def _download_version(db: Session, user: User, version_id: str) -> DocumentVersion:
    """Authorize and return the exact cited version, including non-PDF originals."""
    version, _document = _visible_version(db, user, _parse_uuid(version_id))
    path = Path(version.file_path)

    if not path.is_file():
        raise _err(404, "not_found", "原始檔不存在")

    return version


@router.post("/sources/versions/{version_id}/download-url")
def source_download_url(version_id: str, response: Response, user: User = Depends(require_roles(*ANY_ROLE)),
                        db: Session = Depends(get_db)) -> dict:
    version = _download_version(db, user, version_id)
    ticket = source_downloads.issue(str(user.id), str(version.id), version.file_path)
    response.headers["Cache-Control"] = "no-store"
    return {"url": f"{get_settings().public_base_url.rstrip('/')}/api/sources/download/{ticket}",
            "expires_in": 300}


@router.get("/sources/download/{ticket}")
def signed_source_file(ticket: str, db: Session = Depends(get_db)) -> FileResponse:
    try:
        payload = source_downloads.verify(ticket)
        user = db.get(User, uuid.UUID(payload["user"]))
        if user is None or not user.is_active or user.role not in ANY_ROLE:
            raise ValueError()
        version = _download_version(db, user, payload["version"])
        # Never redirect a capability to a different/newer file at redemption.
        if str(version.id) != payload["version"] or hashlib.sha256(version.file_path.encode()).hexdigest() != payload["file"]:
            raise ValueError()
        source_downloads.claim(db, payload["nonce"])
    except (ValueError, KeyError, TypeError):
        raise _err(403, "invalid_download", "下載連結無效、已使用或已過期")
    audit.record(db, "source.download", actor=user, target_type="document_version", target_id=version.id,
                 meta={"download_nonce": payload["nonce"]})
    db.commit()
    return FileResponse(Path(version.file_path), filename=version.file_name,
                        media_type=version.mime or "application/octet-stream",
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/sources/versions/{version_id}/file")
def source_file(version_id: str, user: User = Depends(require_roles(*ANY_ROLE)), db: Session = Depends(get_db)) -> FileResponse:
    download_version = _download_version(db, user, version_id)
    path = Path(download_version.file_path)

    audit.record(
        db,
        "source.download",
        actor=user,
        target_type="document_version",
        target_id=download_version.id,
    )
    db.commit()

    return FileResponse(
        path,
        filename=download_version.file_name,
        media_type=download_version.mime or "application/octet-stream",
    )


@router.get("/stats/mine")
def my_stats(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """我的使用概況（照服員首頁用）。"""
    open_cases = db.scalar(select(func.count()).select_from(Case).where(Case.created_by == user.id,
                                                                        Case.status != "closed")) or 0
    replied = db.scalar(select(func.count()).select_from(Case).where(Case.created_by == user.id,
                                                                     Case.status == "replied")) or 0
    return {"open_cases": open_cases, "replied_cases": replied}

