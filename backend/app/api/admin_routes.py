"""督導／管理員後台 API。每個端點都限定角色並檢查機構。"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.api.serializers import case_out, version_out
from app.auth import AuthError, create_binding_code, deny_not_found, require_roles, set_password
from app.config import get_settings
from app.db import get_db
from app.models import (
    AuditLog,
    AuthSession,
    BindingCode,
    Case,
    Category,
    CategoryTemplate,
    DeidTerm,
    Document,
    DocumentVersion,
    Feedback,
    LineAccount,
    NotificationJob,
    QaItem,
    TtsAsset,
    User,
)
from app.services import audit, cases, notifications
from app.services import documents as doc_service
from app.services.deid import term_hmac
from app.services.metrics import compute_metrics

router = APIRouter(prefix="/admin")
SUP = ("supervisor", "admin")
DELETED_USERNAME_PREFIX = "__deleted__"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise _err(404, "not_found", "找不到資料") from exc


def _org_case(db: Session, user: User, case_id: str) -> Case:
    case = db.get(Case, _uuid(case_id))
    if case is None:
        raise _err(404, "not_found", "找不到資料")
    if case.org_id != user.org_id:
        raise deny_not_found(db, user, "case", case_id)
    return case


# ── 案件 ─────────────────────────────────────────────────────────────


@router.get("/cases")
def list_cases(status: str | None = None, category_id: str | None = None, assignee_id: str | None = None,
               mine: bool = False, q: str | None = None, include_test: bool = False,
               user: User = Depends(require_roles(*SUP)),
               db: Session = Depends(get_db)) -> list[dict]:
    """案件列表與篩選。"""
    original_username = select(AuditLog.meta["original_username"].astext).where(
        AuditLog.target_id == cast(User.id, String), AuditLog.org_id == User.org_id,
        AuditLog.target_type == "user", AuditLog.action == "user.delete",
    ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(1).correlate(User).scalar_subquery()
    test_creator = select(User.id).where(
        User.id == Case.created_by,
        or_(User.username.startswith("test_", autoescape=True),
            User.username.startswith(DELETED_USERNAME_PREFIX, autoescape=True)
            & original_username.startswith("test_", autoescape=True)),
    ).correlate(Case).exists()
    stmt = select(Case, test_creator.label("is_test")).where(Case.org_id == user.org_id)
    if not include_test:
        # EXISTS preserves cases without a creator and filters before the 200-row limit.
        stmt = stmt.where(~test_creator)
    if status:
        stmt = stmt.where(Case.status.in_(status.split(",")))
    if category_id:
        stmt = stmt.where(Case.category_id == _uuid(category_id))
    if assignee_id == "none":
        stmt = stmt.where(Case.assignee_id.is_(None))
    elif assignee_id:
        stmt = stmt.where(Case.assignee_id == _uuid(assignee_id))
    if mine:
        stmt = stmt.where(Case.assignee_id == user.id)
    if q:
        stmt = stmt.where(or_(Case.number.ilike(f"%{q}%"), Case.summary_masked.ilike(f"%{q}%")))
    rows = db.execute(stmt.order_by(Case.created_at.desc()).limit(200))
    out = []
    for case, is_test in rows:
        category = db.get(Category, case.category_id) if case.category_id else None
        assignee = db.get(User, case.assignee_id) if case.assignee_id else None
        creator = db.get(User, case.created_by)
        out.append({"id": str(case.id), "number": case.number, "status": case.status,
                    "status_label": cases.STATUS_LABELS[case.status], "source_label": cases.SOURCE_LABELS[case.source],
                    "category": category.name if category else None, "reason": case.reason,
                    "summary_masked": case.summary_masked[:120], "created_at": case.created_at.isoformat(),
                    "assignee": assignee.display_name if assignee else None,
                    "creator": creator.display_name if creator else None,
                    "is_test": bool(is_test)})
    return out


@router.get("/cases/{case_id}")
def admin_case(case_id: str, user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> dict:
    """案件詳情（含 AI 引用、歷程、通知狀態）。"""
    return case_out(db, _org_case(db, user, case_id), include_internal=True)


class AssignIn(BaseModel):
    assignee_id: str


@router.post("/cases/{case_id}/assign")
def assign_case(case_id: str, body: AssignIn, user: User = Depends(require_roles(*SUP)),
                db: Session = Depends(get_db)) -> dict:
    """指派／改派。"""
    case = _org_case(db, user, case_id)
    try:
        cases.assign(db, user, case, _uuid(body.assignee_id))
        db.commit()
    except cases.CaseError as exc:
        raise _err(400, exc.code, str(exc)) from exc
    return case_out(db, case, include_internal=True)


@router.post("/cases/{case_id}/take")
def take_case(case_id: str, user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> dict:
    """接手。"""
    case = _org_case(db, user, case_id)
    try:
        cases.take(db, user, case)
        db.commit()
    except cases.CaseError as exc:
        raise _err(409, exc.code, str(exc)) from exc
    return case_out(db, case, include_internal=True)


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    client_request_id: str = Field(min_length=8, max_length=64)


@router.post("/cases/{case_id}/reply")
def reply_case(case_id: str, body: ReplyIn, user: User = Depends(require_roles(*SUP)),
               db: Session = Depends(get_db)) -> dict:
    """回覆：回覆已保存與通知待送同一交易寫入。"""
    case = _org_case(db, user, case_id)
    try:
        message, notification = cases.reply(db, user, case, body.text, body.client_request_id)
        db.commit()
    except cases.CaseError as exc:
        raise _err(409, exc.code, str(exc)) from exc
    return {"message_id": str(message.id), "reply_saved": True,
            "notification": {"id": str(notification.id), "status": notification.status,
                             "last_error_code": notification.last_error_code},
            "case": case_out(db, case, include_internal=True)}


class CloseIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


@router.post("/cases/{case_id}/close")
def close_case(case_id: str, body: CloseIn, user: User = Depends(require_roles(*SUP)),
               db: Session = Depends(get_db)) -> dict:
    """結案。"""
    case = _org_case(db, user, case_id)
    try:
        cases.close(db, user, case, body.reason)
        db.commit()
    except cases.CaseError as exc:
        raise _err(409, exc.code, str(exc)) from exc
    return case_out(db, case, include_internal=True)


@router.get("/notifications")
def list_notifications(status: str | None = None, user: User = Depends(require_roles(*SUP)),
                       db: Session = Depends(get_db)) -> list[dict]:
    """通知工作與結果（accepted＝LINE 平臺受理，不代表送達）。"""
    stmt = select(NotificationJob).where(NotificationJob.org_id == user.org_id)
    if status:
        stmt = stmt.where(NotificationJob.status.in_(status.split(",")))
    return [{"id": str(n.id), "status": n.status, "source_type": n.source_type, "attempts": n.attempts,
             "last_error_code": n.last_error_code, "case_id": str(n.case_id) if n.case_id else None,
             "created_at": n.created_at.isoformat(), "accepted_at": n.accepted_at.isoformat() if n.accepted_at else None,
             "recipient": (db.get(User, n.recipient_id).display_name if db.get(User, n.recipient_id) else "")}
            for n in db.scalars(stmt.order_by(NotificationJob.created_at.desc()).limit(200))]


@router.post("/notifications/{notification_id}/retry")
def retry_notification(notification_id: str, user: User = Depends(require_roles(*SUP)),
                       db: Session = Depends(get_db)) -> dict:
    """重送通知（沿用同一 retry key）。"""
    notification = db.get(NotificationJob, _uuid(notification_id))
    if notification is None or notification.org_id != user.org_id:
        raise deny_not_found(db, user, "notification", notification_id)
    notifications.retry(db, notification)
    audit.record(db, "notification.retry", actor=user, target_type="notification", target_id=notification.id)
    db.commit()
    return {"status": notification.status}


# ── 文件 ─────────────────────────────────────────────────────────────


def _visible_document(db: Session, user: User, document_id: uuid.UUID, *, write: bool) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise _err(404, "not_found", "找不到資料")
    if document.org_id is not None and document.org_id != user.org_id:
        raise deny_not_found(db, user, "document", document_id)
    if write and document.org_id is None and user.role != "admin":
        raise _err(403, "forbidden", "全機構共用文件只有管理員可以修改")
    return document


@router.get("/documents")
def list_documents(user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> list[dict]:
    """文件與版本一覽。"""
    docs = db.scalars(select(Document).where(or_(Document.org_id.is_(None), Document.org_id == user.org_id))
                      .order_by(Document.doc_type, Document.title))
    today = datetime.now(ZoneInfo(get_settings().tz_name)).date()
    current = set(doc_service.current_versions(db, user.org_id, _facility(db, user), today))
    out = []
    for document in docs:
        versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id)
                              .order_by(DocumentVersion.uploaded_at.desc()))
        out.append({"id": str(document.id), "title": document.title, "doc_type": document.doc_type,
                    "scope": "shared" if document.org_id is None else "org",
                    "facility_types": document.facility_types,
                    "versions": [dict(version_out(db, v), is_current=v.id in current) for v in versions]})
    return out


def _facility(db: Session, user: User) -> str:
    from app.models import Organization

    org = db.get(Organization, user.org_id)
    return org.facility_type if org else "residential"


class DocumentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    doc_type: str
    scope: str = "org"
    facility_types: list[str] = Field(default_factory=lambda: ["residential"])


@router.post("/documents")
def create_document(body: DocumentIn, user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> dict:
    """建立文件。"""
    try:
        document = doc_service.create_document(db, user, title=body.title, doc_type=body.doc_type,
                                               scope=body.scope, facility_types=body.facility_types)
        db.commit()
    except doc_service.DocumentError as exc:
        raise _err(403 if exc.code == "forbidden" else 422, exc.code, str(exc)) from exc
    return {"id": str(document.id)}


def _date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise _err(422, "invalid_date", "日期格式須為 YYYY-MM-DD") from exc


@router.post("/documents/{document_id}/versions")
async def upload_version(
    document_id: str,
    file: UploadFile = File(...),
    version_label: str = Form(...),
    effective_from: str | None = Form(None),
    effective_to: str | None = Form(None),
    source: str | None = Form(None),
    source_url: str | None = Form(None),
    user: User = Depends(require_roles(*SUP)),
    db: Session = Depends(get_db),
) -> dict:
    """上傳新版本（先解析、檢查，發布前不影響現行版本）。"""
    document = _visible_document(db, user, _uuid(document_id), write=True)
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    try:
        version = doc_service.add_version(
            db, user, document, file_name=file.filename or "upload", data=data, version_label=version_label,
            effective_from=_date(effective_from), effective_to=_date(effective_to), source=source,
            source_url=source_url,
        )
        db.commit()
    except doc_service.DocumentError as exc:
        raise _err(413 if exc.code == "too_large" else 422, exc.code, str(exc)) from exc
    return version_out(db, version)


def _visible_version(db: Session, user: User, version_id: str, *, write: bool) -> DocumentVersion:
    version = db.get(DocumentVersion, _uuid(version_id))
    if version is None:
        raise _err(404, "not_found", "找不到資料")
    _visible_document(db, user, version.document_id, write=write)
    return version


@router.get("/versions/{version_id}")
def get_version(version_id: str, user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> dict:
    """版本預覽（切塊、待補欄位、解析警告）。"""
    return version_out(db, _visible_version(db, user, version_id, write=False), with_chunks=True)


class VersionPatch(BaseModel):
    effective_from: str | None = None
    effective_to: str | None = None
    source: str | None = Field(default=None, max_length=300)
    source_url: str | None = Field(default=None, max_length=500)


@router.patch("/versions/{version_id}")
def patch_version(version_id: str, body: VersionPatch, user: User = Depends(require_roles(*SUP)),
                  db: Session = Depends(get_db)) -> dict:
    """補中繼資料（已發布版本不可改日期，避免改寫歷史）。"""
    version = _visible_version(db, user, version_id, write=True)
    if version.status not in {"review", "parse_failed", "uploaded", "parsing"}:
        raise _err(409, "invalid_state", "已發布或停用的版本不能修改；請上傳新版本")
    fields = body.model_dump(exclude_unset=True)
    if "effective_from" in fields:
        version.effective_from = _date(fields["effective_from"])
    if "effective_to" in fields:
        version.effective_to = _date(fields["effective_to"])
    if version.effective_from and version.effective_to and version.effective_to < version.effective_from:
        raise _err(422, "invalid_dates", "失效日不可早於生效日")
    if "source" in fields:
        version.source = (fields["source"] or "").strip() or None
    if "source_url" in fields:
        url = (fields["source_url"] or "").strip()
        if url and not url.startswith(("http://", "https://")):
            raise _err(422, "invalid_source_url", "出處網址須為 http(s)")
        version.source_url = url or None
    audit.record(db, "doc.update_meta", actor=user, target_type="document_version", target_id=version.id,
                 meta={"fields": sorted(fields)})
    db.commit()
    return version_out(db, version)


@router.post("/versions/{version_id}/publish")
def publish_version(version_id: str, user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> dict:
    """發布（待補欄位須清空）。"""
    version = _visible_version(db, user, version_id, write=True)
    try:
        doc_service.publish(db, user, version)
        db.commit()
    except doc_service.DocumentError as exc:
        raise _err(422, exc.code, str(exc)) from exc
    return version_out(db, version)


@router.post("/versions/{version_id}/deactivate")
def deactivate_version(version_id: str, user: User = Depends(require_roles(*SUP)),
                       db: Session = Depends(get_db)) -> dict:
    """停用。"""
    version = _visible_version(db, user, version_id, write=True)
    try:
        doc_service.deactivate(db, user, version)
        db.commit()
    except doc_service.DocumentError as exc:
        raise _err(409, exc.code, str(exc)) from exc
    return version_out(db, version)


# ── 分類設定 ─────────────────────────────────────────────────────────


def _categories_out(db: Session, org_id: uuid.UUID) -> list[dict]:
    out = []
    for category in db.scalars(select(Category).where(Category.org_id == org_id)
                               .order_by(Category.sort_order, Category.name)):
        templates = db.scalars(select(CategoryTemplate).where(CategoryTemplate.category_id == category.id)
                               .order_by(CategoryTemplate.sort_order))
        assignee = db.get(User, category.default_assignee_id) if category.default_assignee_id else None
        out.append({"id": str(category.id), "name": category.name, "description": category.description,
                    "sort_order": category.sort_order, "is_active": category.is_active,
                    "default_assignee": {"id": str(assignee.id), "display_name": assignee.display_name}
                    if assignee else None,
                    "templates": [{"id": str(t.id), "text": t.text, "is_active": t.is_active,
                                   "sort_order": t.sort_order} for t in templates]})
    return out


@router.get("/categories")
def admin_categories(user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> list[dict]:
    """分類設定一覽（督導可檢視，管理員可修改）。"""
    return _categories_out(db, user.org_id)


class TemplateIn(BaseModel):
    id: str | None = None
    text: str = Field(min_length=1, max_length=200)
    is_active: bool = True


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=200)
    sort_order: int = 0
    is_active: bool = True
    default_assignee_id: str | None = None
    templates: list[TemplateIn] = Field(default_factory=list)


def _apply_category(db: Session, user: User, category: Category, body: CategoryIn) -> None:
    category.name = body.name.strip()
    category.description = body.description
    category.sort_order = body.sort_order
    category.is_active = body.is_active
    if body.default_assignee_id:
        assignee = db.get(User, _uuid(body.default_assignee_id))
        if assignee is None or assignee.org_id != user.org_id or assignee.role not in SUP:
            raise _err(422, "invalid_assignee", "預設督導必須是同機構督導")
        category.default_assignee_id = assignee.id
    else:
        category.default_assignee_id = None
    db.flush()
    existing = {str(t.id): t for t in db.scalars(select(CategoryTemplate).where(
        CategoryTemplate.category_id == category.id))}
    keep = set()
    for order, tmpl in enumerate(body.templates):
        if tmpl.id and tmpl.id in existing:
            row = existing[tmpl.id]
            row.text, row.is_active, row.sort_order = tmpl.text.strip(), tmpl.is_active, order
            keep.add(tmpl.id)
        else:
            db.add(CategoryTemplate(category_id=category.id, text=tmpl.text.strip(), is_active=tmpl.is_active,
                                    sort_order=order))
    for tid, row in existing.items():
        if tid not in keep:
            row.is_active = False  # 不刪除，保留歷史案件可讀性


@router.post("/categories")
def create_category(body: CategoryIn, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)) -> list[dict]:
    """新增分類。"""
    if db.scalar(select(Category.id).where(Category.org_id == user.org_id, Category.name == body.name.strip())):
        raise _err(409, "duplicate", "分類名稱重複")
    category = Category(org_id=user.org_id, name=body.name.strip())
    db.add(category)
    _apply_category(db, user, category, body)
    audit.record(db, "category.create", actor=user, target_type="category", target_id=category.id)
    db.commit()
    return _categories_out(db, user.org_id)


@router.put("/categories/{category_id}")
def update_category(category_id: str, body: CategoryIn, user: User = Depends(require_roles("admin")),
                    db: Session = Depends(get_db)) -> list[dict]:
    """修改分類與模板。"""
    category = db.get(Category, _uuid(category_id))
    if category is None or category.org_id != user.org_id:
        raise deny_not_found(db, user, "category", category_id)
    _apply_category(db, user, category, body)
    audit.record(db, "category.update", actor=user, target_type="category", target_id=category.id)
    db.commit()
    return _categories_out(db, user.org_id)


# ── 回饋、指標、稽核 ──────────────────────────────────────────────────


@router.get("/feedback")
def list_feedback(user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> list[dict]:
    """回答回饋（回答有誤優先）。"""
    rows = db.execute(select(Feedback, QaItem).join(QaItem, QaItem.id == Feedback.qa_item_id)
                      .where(Feedback.org_id == user.org_id).order_by(Feedback.created_at.desc()).limit(200)).all()
    return [{"id": str(f.id), "kind": f.kind, "status": f.status, "reason": f.reason_masked,
             "created_at": f.created_at.isoformat(), "qa_item_id": str(q.id), "question_masked": q.question_masked,
             "answer_text": q.answer_text, "outcome": q.outcome} for f, q in rows]


@router.post("/feedback/{feedback_id}/review")
def review_feedback(feedback_id: str, user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> dict:
    """標記回饋已檢視。"""
    row = db.get(Feedback, _uuid(feedback_id))
    if row is None or row.org_id != user.org_id:
        raise deny_not_found(db, user, "feedback", feedback_id)
    row.status, row.reviewed_by = "reviewed", user.id
    from app.services.jobs import utcnow

    row.reviewed_at = utcnow()
    audit.record(db, "feedback.review", actor=user, target_type="feedback", target_id=row.id)
    db.commit()
    return {"ok": True}


@router.get("/metrics")
def metrics(days: int = 30, user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> dict:
    """治理指標（每項附分子、分母與定義）。"""
    days = max(1, min(days, 365))
    return compute_metrics(db, user.org_id, _facility(db, user), days)


@router.get("/audit")
def list_audit(action: str | None = None, limit: int = 200, user: User = Depends(require_roles("admin")),
               db: Session = Depends(get_db)) -> list[dict]:
    """稽核紀錄（本機構）。"""
    stmt = select(AuditLog).where(AuditLog.org_id == user.org_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).limit(max(1, min(limit, 1000))))
    return [{"id": r.id, "created_at": r.created_at.isoformat(), "action": r.action, "outcome": r.outcome,
             "actor_role": r.actor_role, "actor": (db.get(User, r.actor_id).display_name
                                                   if r.actor_id and db.get(User, r.actor_id) else None),
             "target_type": r.target_type, "target_id": r.target_id, "meta": r.meta} for r in rows]


# ── 帳號 ─────────────────────────────────────────────────────────────


@router.get("/users")
def list_users(include_deleted: bool = False, user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> list[dict]:
    """同機構帳號（督導可看，用於指派；管理員可管理）。"""
    stmt = select(User).where(User.org_id == user.org_id)
    if not include_deleted:
        stmt = stmt.where(~User.username.startswith(DELETED_USERNAME_PREFIX, autoescape=True))
    rows = db.scalars(stmt.order_by(User.role, User.display_name))
    out = []
    for row in rows:
        account = db.scalar(select(LineAccount).where(LineAccount.user_id == row.id))
        is_deleted = row.username.startswith(DELETED_USERNAME_PREFIX)
        deletion = db.scalar(select(AuditLog).where(AuditLog.target_id == str(row.id), AuditLog.action == "user.delete").order_by(AuditLog.created_at.desc())) if is_deleted else None
        out.append({"id": str(row.id), "username": row.username, "display_name": row.display_name, "role": row.role,
                    "is_active": row.is_active, "line_bound": account is not None,
                    "line_blocked": bool(account and account.is_blocked), "is_deleted": is_deleted,
                    "original_username": deletion.meta.get("original_username") if deletion else None})
    return out


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.\-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    role: str = Field(pattern="^(caregiver|supervisor|admin)$")
    password: str | None = Field(default=None, max_length=200)


@router.post("/users")
def create_user(body: UserIn, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)) -> dict:
    """新增帳號（照服員不需密碼，以綁定碼連 LINE）。"""
    if body.username.startswith(DELETED_USERNAME_PREFIX):
        raise _err(422, "reserved_username", "此帳號前綴為系統保留")
    if db.scalar(select(User.id).where(User.username == body.username)):
        raise _err(409, "duplicate", "帳號已存在")
    new_user = User(org_id=user.org_id, username=body.username, display_name=body.display_name, role=body.role)
    if body.role != "caregiver":
        if not body.password:
            raise _err(422, "password_required", "督導與管理員須設定密碼")
        try:
            set_password(new_user, body.password)
        except AuthError as exc:
            raise _err(422, exc.code, str(exc)) from exc
    db.add(new_user)
    db.flush()
    audit.record(db, "user.create", actor=user, target_type="user", target_id=new_user.id, meta={"role": body.role})
    db.commit()
    return {"id": str(new_user.id)}


@router.post("/users/{user_id}/binding-code")
def binding_code(user_id: str, user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> dict:
    """產生 LINE 綁定碼（明文只顯示這一次）。"""
    target = db.scalar(select(User).where(User.id == _uuid(user_id)).with_for_update())
    if target is None or target.org_id != user.org_id:
        raise deny_not_found(db, user, "user", user_id)
    if target.role != "caregiver":
        raise _err(403, "caregiver_required", "僅能替照服員產生綁定碼")
    if not target.is_active:
        raise _err(409, "inactive", "帳號已停用，無法產生綁定碼")
    code = create_binding_code(db, user, target)
    db.commit()
    return {"code": code, "expires_in_days": 7}


class UserActiveIn(BaseModel):
    is_active: bool


@router.patch("/users/{user_id}/active")
def set_user_active(user_id: str, body: UserActiveIn, user: User = Depends(require_roles("admin")),
                    db: Session = Depends(get_db)) -> dict:
    """啟用／停用同機構帳號；保留帳號與所有歷史資料。"""
    target = db.scalar(select(User).where(User.id == _uuid(user_id)).with_for_update())
    if target is None or target.org_id != user.org_id:
        raise deny_not_found(db, user, "user", user_id)
    if target.username.startswith(DELETED_USERNAME_PREFIX):
        raise _err(409, "deleted_user", "已刪除帳號不可重新啟用，請建立新帳號")
    target.is_active = body.is_active
    if not body.is_active:
        now = datetime.now(ZoneInfo("UTC"))
        db.execute(update(AuthSession).where(AuthSession.user_id == target.id,
                       AuthSession.revoked_at.is_(None)).values(revoked_at=now))
        db.execute(update(BindingCode).where(BindingCode.user_id == target.id,
                       BindingCode.used_at.is_(None)).values(expires_at=now))
    audit.record(db, "user.active", actor=user, target_type="user", target_id=target.id,
                 meta={"is_active": body.is_active})
    db.commit()
    return {"id": str(target.id), "is_active": target.is_active}


@router.delete("/users/{user_id}/line-binding")
def unbind_line(user_id: str, user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> dict:
    """解除同機構綁定；督導僅可操作 caregiver，admin 可操作同機構帳號。"""
    target = db.scalar(select(User).where(User.id == _uuid(user_id)).with_for_update())
    if target is None or target.org_id != user.org_id:
        raise deny_not_found(db, user, "user", user_id)
    if user.role == "supervisor" and target.role != "caregiver":
        raise _err(403, "caregiver_required", "督導僅能解除照服員綁定")
    now = datetime.now(ZoneInfo("UTC"))
    db.execute(delete(LineAccount).where(LineAccount.user_id == target.id))
    db.execute(update(AuthSession).where(AuthSession.user_id == target.id,
                   AuthSession.kind.in_(["liff", "dev"]), AuthSession.revoked_at.is_(None)).values(revoked_at=now))
    db.execute(update(BindingCode).where(BindingCode.user_id == target.id,
                   BindingCode.used_at.is_(None)).values(expires_at=now))
    audit.record(db, "user.line_unbind", actor=user, target_type="user", target_id=target.id)
    db.commit()
    return {"id": str(target.id), "line_bound": False}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)) -> dict:
    """Soft delete: keep UUID/display name/history, release username atomically."""
    target = db.scalar(select(User).where(User.id == _uuid(user_id)).with_for_update())
    if target is None or target.org_id != user.org_id:
        raise deny_not_found(db, user, "user", user_id)
    if target.id == user.id:
        raise _err(409, "self_delete", "不可刪除目前登入的管理員帳號")
    if target.username.startswith(DELETED_USERNAME_PREFIX):
        return {"id": str(target.id), "deleted": True}
    original_username = target.username
    now = datetime.now(ZoneInfo("UTC"))
    target.username = DELETED_USERNAME_PREFIX + target.id.hex
    target.is_active = False
    target.password_hash = None
    db.execute(delete(LineAccount).where(LineAccount.user_id == target.id))
    db.execute(update(AuthSession).where(AuthSession.user_id == target.id,
                   AuthSession.revoked_at.is_(None)).values(revoked_at=now))
    db.execute(update(BindingCode).where(BindingCode.user_id == target.id,
                   BindingCode.used_at.is_(None)).values(expires_at=now))
    assets = db.scalars(select(TtsAsset).where(TtsAsset.qa_item_id.in_(
                       select(QaItem.id).where(QaItem.user_id == target.id))).with_for_update())
    for asset in assets:
        asset.expires_at = now
        asset.token_id = uuid.uuid4().hex  # Existing signed audio URLs no longer resolve.
    # Account identifier only, never password/token/LINE identity or question text.
    audit.record(db, "user.delete", actor=user, target_type="user", target_id=target.id,
                 meta={"original_username": original_username})
    db.commit()
    return {"id": str(target.id), "deleted": True}


class DeidTermIn(BaseModel):
    term: str = Field(min_length=2, max_length=8)


@router.post("/deid-terms")
def add_deid_term(body: DeidTermIn, user: User = Depends(require_roles(*SUP)), db: Session = Depends(get_db)) -> dict:
    """新增機構自訂遮罩詞（只存 HMAC，不存明文）。"""
    digest = term_hmac(body.term.strip())
    if not db.scalar(select(DeidTerm.id).where(DeidTerm.org_id == user.org_id, DeidTerm.term_hmac == digest)):
        db.add(DeidTerm(org_id=user.org_id, term_hmac=digest, length=len(body.term.strip()), created_by=user.id))
        audit.record(db, "deid.term_add", actor=user)
        db.commit()
    count = db.scalar(select(func.count()).select_from(DeidTerm).where(DeidTerm.org_id == user.org_id))
    return {"count": count}
