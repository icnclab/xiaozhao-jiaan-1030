"""GA09/SC09 服務紀錄草稿：服務個案主檔、明確授權、草稿建立/更新/送出、主任/admin 核准表單範本。

服務個案（jiaan1030_service_clients）代表受照顧者，獨立於 cases（督導問題回報工單）——
cases 語意上是照服員問題回報，不適合代表「某受照顧者的某次服務紀錄」。

存取政策（保守預設，無明確授權規則前；支援跨居督共用照服員）：
- 服務個案：建立者可讀寫；任何角色（含照服員）僅在「同機構」且存在未撤銷的明確授權
  （jiaan1030_service_client_grants）時才可存取；兩者皆不滿足一律視為不存在（404）。
  - 被授權的**照服員**：可唯讀個案，且可用該個案**建立自己的**服務草稿（支援跨居督共用照服員）。
  - 被授權的**督導/主任/admin**：僅可唯讀個案與草稿，不可建立/修改/送出草稿（唯讀，不得擅自擴權）。
- 草稿：沿用同一存取規則（建立者可讀寫；有授權者可唯讀）；**無論角色，一律不可修改或送出他人建立的草稿**。
- 授權的建立/撤銷：只有服務個案的建立者，或主任/admin（經授權管理者），才能新增或撤銷他人的存取授權；
  督導即使自己有唯讀授權，也不可再授權第三人（避免擅自擴權）。

未核准（reviewed=FALSE 或 schema_status!='approved'）的表單一律不可送出，只能停留在草稿狀態。
稽核 meta 只放代碼、ID 與狀態轉換，不放 payload_json 內容或 display_label 等可能含代稱的欄位。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import roles
from app.auth import current_user, deny_not_found, require_roles
from app.db import get_db
from app.jiaan1030_client_models import Jiaan1030ServiceClient, Jiaan1030ServiceClientGrant
from app.jiaan1030_draft_models import Jiaan1030ServiceFormDraft
from app.models import User
from app.services import audit

router = APIRouter()


def _err(status: int, code: str, message: str):
    from fastapi import HTTPException

    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _parse_uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise _err(400, "invalid_id", "格式錯誤")


def _form_row(db: Session, form_code: str) -> dict | None:
    row = db.execute(
        text("SELECT code, title, fields_json, reviewed, schema_status FROM jiaan1030_service_forms WHERE code = :code"),
        {"code": form_code},
    ).mappings().first()
    return dict(row) if row else None


def _active_grant(db: Session, client_id: uuid.UUID, user_id: uuid.UUID) -> Jiaan1030ServiceClientGrant | None:
    return db.query(Jiaan1030ServiceClientGrant).filter_by(
        service_client_id=client_id, grantee_id=user_id, revoked_at=None
    ).first()


def _has_client_access(db: Session, user: User, client: Jiaan1030ServiceClient) -> bool:
    """建立者可讀寫；任何角色（含照服員，支援跨居督共用）僅在同機構且有未撤銷的
    明確授權時才可存取；角色決定授權後能做什麼（照服員可建立自己的草稿，督導/主任/admin 僅唯讀），
    但「看不看得到」這一層一律同規則，不因角色而放寬。"""
    # Check tenant before ownership: a moved user must never retain access
    # to records belonging to their previous organisation.
    if client.org_id != user.org_id:
        return False
    if client.created_by == user.id:
        return True
    return _active_grant(db, client.id, user.id) is not None


def _can_create_draft_for_client(db: Session, user: User, client: Jiaan1030ServiceClient) -> bool:
    """建立者可建立草稿；被授權的照服員可建立自己的草稿（跨居督共用）；
    被授權的督導/主任/admin 僅唯讀，不可建立草稿（不得擅自擴權）。"""
    if client.org_id != user.org_id:
        return False
    if client.created_by == user.id:
        return True
    if user.role in roles.REVIEWERS:
        return False
    return _active_grant(db, client.id, user.id) is not None


def _visible_client(db: Session, user: User, client_id: str) -> Jiaan1030ServiceClient:
    client = db.get(Jiaan1030ServiceClient, _parse_uuid(client_id))
    if client is None:
        raise _err(404, "not_found", "找不到資料")
    if not _has_client_access(db, user, client):
        raise deny_not_found(db, user, "jiaan1030_service_client", client_id)
    return client


def _client_out(client: Jiaan1030ServiceClient) -> dict:
    return {
        "id": str(client.id),
        "display_label": client.display_label,
        "created_at": client.created_at.isoformat(),
        "created_by": str(client.created_by),
    }


def _grant_out(grant: Jiaan1030ServiceClientGrant) -> dict:
    return {
        "id": str(grant.id),
        "service_client_id": str(grant.service_client_id),
        "grantee_id": str(grant.grantee_id),
        "granted_by": str(grant.granted_by),
        "created_at": grant.created_at.isoformat(),
        "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
    }


def _visible_draft(db: Session, user: User, draft_id: str) -> Jiaan1030ServiceFormDraft:
    draft = db.get(Jiaan1030ServiceFormDraft, _parse_uuid(draft_id))
    if draft is None:
        raise _err(404, "not_found", "找不到資料")
    # A user moved to another organisation must not read an old draft,
    # including drafts they originally created.
    if draft.org_id != user.org_id:
        raise deny_not_found(db, user, "jiaan1030_service_form_draft", draft_id)
    owns_it = draft.created_by == user.id
    has_client_access = False
    if not owns_it:
        client = db.get(Jiaan1030ServiceClient, draft.service_client_id)
        has_client_access = client is not None and _has_client_access(db, user, client)
    if not owns_it and not has_client_access:
        raise deny_not_found(db, user, "jiaan1030_service_form_draft", draft_id)
    return draft


def _draft_out(draft: Jiaan1030ServiceFormDraft) -> dict:
    return {
        "id": str(draft.id),
        "service_client_id": str(draft.service_client_id),
        "form_code": draft.form_code,
        "payload": draft.payload_json,
        "status": draft.status,
        "created_by": str(draft.created_by),
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
        "submitted_at": draft.submitted_at.isoformat() if draft.submitted_at else None,
    }


class CreateClientBody(BaseModel):
    display_label: str


class GrantBody(BaseModel):
    grantee_id: str


class CreateDraftBody(BaseModel):
    service_client_id: str
    form_code: str
    payload: dict = {}
    client_request_id: str


class UpdateDraftBody(BaseModel):
    payload: dict


class ApproveFormBody(BaseModel):
    schema_status: str | None = None
    reviewed: bool | None = None


# ── 服務個案主檔（最小化，僅供假資料測試） ──────────────────────────────

@router.post("/jiaan1030/service-clients", status_code=201)
def create_service_client(
    body: CreateClientBody,
    user: User = Depends(require_roles(*roles.ALL_STAFF)),
    db: Session = Depends(get_db),
) -> dict:
    label = body.display_label.strip()
    if not label:
        raise _err(400, "empty", "請輸入服務個案代稱（請用假資料/代稱，不要填真實姓名）")
    client = Jiaan1030ServiceClient(org_id=user.org_id, created_by=user.id, display_label=label[:100])
    db.add(client)
    db.flush()
    audit.record(db, "jiaan1030_client.create", actor=user, target_type="jiaan1030_service_client",
                 target_id=client.id)
    db.commit()
    return _client_out(client)


@router.get("/jiaan1030/service-clients")
def list_service_clients(
    user: User = Depends(require_roles(*roles.ALL_STAFF)), db: Session = Depends(get_db)
) -> list[dict]:
    granted_ids = db.query(Jiaan1030ServiceClientGrant.service_client_id).filter(
        Jiaan1030ServiceClientGrant.grantee_id == user.id,
        Jiaan1030ServiceClientGrant.revoked_at.is_(None),
    )
    query = db.query(Jiaan1030ServiceClient).filter(
        Jiaan1030ServiceClient.org_id == user.org_id,
        or_(Jiaan1030ServiceClient.created_by == user.id, Jiaan1030ServiceClient.id.in_(granted_ids)),
    )
    rows = query.order_by(Jiaan1030ServiceClient.created_at.desc()).limit(200).all()
    return [_client_out(r) for r in rows]


@router.get("/jiaan1030/grantable-reviewers")
def list_grantable_reviewers(
    user: User = Depends(require_roles(*roles.ALL_STAFF)),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Minimal same-organization roster; no email, LINE identifiers or credentials."""
    rows = db.query(User).filter(
        User.org_id == user.org_id,
        User.is_active.is_(True),
        User.role.in_(["supervisor", "director", "admin"]),
    ).order_by(User.role, User.username).limit(100).all()
    return [{"id": str(u.id), "display_name": u.display_name,
             "username": u.username, "role": u.role} for u in rows]


@router.get("/jiaan1030/service-clients/{client_id}/grants")
def list_client_grants(
    client_id: str,
    user: User = Depends(require_roles(*roles.ALL_STAFF)),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Only the client creator or an authorized approver can inspect grant state.

    No extra tenant/role privilege is conferred by this endpoint.
    """
    client = _visible_client(db, user, client_id)
    if client.created_by != user.id and user.role not in roles.APPROVERS:
        raise _err(403, "forbidden", "只有建立者或主任/admin 可以檢視授權清單")
    rows = db.query(Jiaan1030ServiceClientGrant, User).join(
        User, User.id == Jiaan1030ServiceClientGrant.grantee_id
    ).filter(
        Jiaan1030ServiceClientGrant.service_client_id == client.id,
        User.org_id == user.org_id,
    ).order_by(Jiaan1030ServiceClientGrant.created_at.desc()).limit(100).all()
    return [dict(**_grant_out(grant), grantee_name=person.display_name,
                 grantee_username=person.username, grantee_role=person.role)
            for grant, person in rows]


@router.post("/jiaan1030/service-clients/{client_id}/grants", status_code=201)
def grant_client_access(
    client_id: str,
    body: GrantBody,
    user: User = Depends(require_roles(*roles.ALL_STAFF)),
    db: Session = Depends(get_db),
) -> dict:
    client = db.get(Jiaan1030ServiceClient, _parse_uuid(client_id))
    if client is None:
        raise _err(404, "not_found", "找不到資料")
    if not _has_client_access(db, user, client):
        raise deny_not_found(db, user, "jiaan1030_service_client", client_id)
    if client.created_by != user.id and user.role not in roles.APPROVERS:
        raise _err(403, "forbidden", "只有建立者或主任/admin 可以授權他人查看此服務個案")
    grantee = db.get(User, _parse_uuid(body.grantee_id))
    if grantee is None or grantee.org_id != user.org_id or not grantee.is_active:
        raise _err(400, "invalid_grantee", "被授權人必須是同機構的現職使用者")
    if grantee.id == client.created_by:
        raise _err(400, "invalid_grantee", "建立者本身已有完整存取權限，不需另外授權")
    existing = db.query(Jiaan1030ServiceClientGrant).filter_by(
        service_client_id=client.id, grantee_id=grantee.id
    ).first()
    if existing is not None:
        if existing.revoked_at is not None:
            existing.revoked_at = None
            db.flush()
            audit.record(db, "jiaan1030_client.grant", actor=user, target_type="jiaan1030_service_client",
                         target_id=client.id, meta={"grantee_id": str(grantee.id), "action": "re_grant"})
            db.commit()
        return _grant_out(existing)
    grant = Jiaan1030ServiceClientGrant(service_client_id=client.id, grantee_id=grantee.id, granted_by=user.id)
    db.add(grant)
    db.flush()
    audit.record(db, "jiaan1030_client.grant", actor=user, target_type="jiaan1030_service_client",
                 target_id=client.id, meta={"grantee_id": str(grantee.id), "action": "grant"})
    db.commit()
    return _grant_out(grant)


@router.post("/jiaan1030/service-clients/{client_id}/grants/{grantee_id}/revoke")
def revoke_client_access(
    client_id: str,
    grantee_id: str,
    user: User = Depends(require_roles(*roles.ALL_STAFF)),
    db: Session = Depends(get_db),
) -> dict:
    client = db.get(Jiaan1030ServiceClient, _parse_uuid(client_id))
    if client is None:
        raise _err(404, "not_found", "找不到資料")
    if not _has_client_access(db, user, client):
        raise deny_not_found(db, user, "jiaan1030_service_client", client_id)
    if client.created_by != user.id and user.role not in roles.APPROVERS:
        raise _err(403, "forbidden", "只有建立者或主任/admin 可以撤銷授權")
    grant = db.query(Jiaan1030ServiceClientGrant).filter_by(
        service_client_id=client.id, grantee_id=_parse_uuid(grantee_id)
    ).first()
    if grant is None or grant.revoked_at is not None:
        raise _err(404, "not_found", "找不到有效授權")
    from app.services import jobs

    grant.revoked_at = jobs.utcnow()
    db.flush()
    audit.record(db, "jiaan1030_client.revoke", actor=user, target_type="jiaan1030_service_client",
                 target_id=client.id, meta={"grantee_id": str(grant.grantee_id)})
    db.commit()
    return _grant_out(grant)


# ── 草稿 ────────────────────────────────────────────────────────────

@router.post("/jiaan1030/service-drafts", status_code=201)
def create_draft(
    body: CreateDraftBody,
    user: User = Depends(require_roles(*roles.ALL_STAFF)),
    db: Session = Depends(get_db),
) -> dict:
    existing = db.query(Jiaan1030ServiceFormDraft).filter_by(
        created_by=user.id, client_request_id=body.client_request_id
    ).first()
    if existing is not None:
        return _draft_out(existing)
    client = db.get(Jiaan1030ServiceClient, _parse_uuid(body.service_client_id))
    if client is None or client.org_id != user.org_id:
        raise deny_not_found(db, user, "jiaan1030_service_client", body.service_client_id)
    if not _has_client_access(db, user, client):
        raise deny_not_found(db, user, "jiaan1030_service_client", body.service_client_id)
    if not _can_create_draft_for_client(db, user, client):
        # 看得到（有唯讀授權）但不能建立草稿：督導/主任/admin 透過授權僅唯讀，不得擅自擴權。
        audit.record(db, "jiaan1030_draft.forbidden", actor=user, target_type="jiaan1030_service_client",
                     target_id=client.id, outcome="denied", meta={"action": "create_draft"})
        db.commit()
        raise _err(403, "forbidden", "此身分對該服務個案僅有唯讀授權，不可建立服務草稿")
    form = _form_row(db, body.form_code)
    if form is None:
        raise _err(404, "not_found", "找不到表單範本")
    draft = Jiaan1030ServiceFormDraft(
        org_id=user.org_id,
        service_client_id=client.id,
        form_code=body.form_code,
        client_request_id=body.client_request_id,
        payload_json=body.payload,
        status="draft",
        created_by=user.id,
    )
    db.add(draft)
    try:
        db.flush()
        audit.record(db, "jiaan1030_draft.create", actor=user, target_type="jiaan1030_service_form_draft",
                     target_id=draft.id, meta={"form_code": draft.form_code, "service_client_id": str(draft.service_client_id)})
        db.commit()
    except IntegrityError:
        # 同一瀏覽器分頁的重複呼叫（例如 React StrictMode 雙重掛載或網路重試）以同一
        # client_request_id 併發送出：唯一索引保障不會重複建立草稿，改回傳既有草稿。
        db.rollback()
        existing = db.query(Jiaan1030ServiceFormDraft).filter_by(
            created_by=user.id, client_request_id=body.client_request_id
        ).first()
        if existing is None:
            raise
        return _draft_out(existing)
    return _draft_out(draft)


@router.get("/jiaan1030/service-drafts")
def list_drafts(user: User = Depends(require_roles(*roles.ALL_STAFF)), db: Session = Depends(get_db)) -> list[dict]:
    granted_ids = db.query(Jiaan1030ServiceClientGrant.service_client_id).filter(
        Jiaan1030ServiceClientGrant.grantee_id == user.id,
        Jiaan1030ServiceClientGrant.revoked_at.is_(None),
    )
    accessible_clients = db.query(Jiaan1030ServiceClient.id).filter(
        Jiaan1030ServiceClient.org_id == user.org_id,
        or_(Jiaan1030ServiceClient.created_by == user.id, Jiaan1030ServiceClient.id.in_(granted_ids)),
    )
    query = db.query(Jiaan1030ServiceFormDraft).filter(
        Jiaan1030ServiceFormDraft.service_client_id.in_(accessible_clients)
    )
    rows = query.order_by(Jiaan1030ServiceFormDraft.updated_at.desc()).limit(100).all()
    return [_draft_out(r) for r in rows]


@router.patch("/jiaan1030/service-drafts/{draft_id}")
def update_draft(
    draft_id: str,
    body: UpdateDraftBody,
    user: User = Depends(require_roles(*roles.ALL_STAFF)),
    db: Session = Depends(get_db),
) -> dict:
    draft = _visible_draft(db, user, draft_id)
    if draft.created_by != user.id:
        audit.record(db, "jiaan1030_draft.forbidden", actor=user, target_type="jiaan1030_service_form_draft",
                     target_id=draft.id, outcome="denied", meta={"action": "update"})
        db.commit()
        raise _err(403, "forbidden", "只能修改自己的草稿")
    if draft.status != "draft":
        raise _err(409, "already_submitted", "已送出的草稿不可修改")
    draft.payload_json = body.payload
    draft.updated_by = user.id
    db.flush()
    audit.record(db, "jiaan1030_draft.update", actor=user, target_type="jiaan1030_service_form_draft",
                 target_id=draft.id, meta={"form_code": draft.form_code})
    db.commit()
    return _draft_out(draft)


@router.post("/jiaan1030/service-drafts/{draft_id}/submit")
def submit_draft(
    draft_id: str,
    user: User = Depends(require_roles(*roles.ALL_STAFF)),
    db: Session = Depends(get_db),
) -> dict:
    draft = _visible_draft(db, user, draft_id)
    if draft.created_by != user.id:
        audit.record(db, "jiaan1030_draft.forbidden", actor=user, target_type="jiaan1030_service_form_draft",
                     target_id=draft.id, outcome="denied", meta={"action": "submit"})
        db.commit()
        raise _err(403, "forbidden", "只能送出自己的草稿")
    if draft.status == "submitted":
        return _draft_out(draft)
    form = _form_row(db, draft.form_code)
    if form is None or not form["reviewed"] or form["schema_status"] != "approved":
        raise _err(409, "form_not_approved", "表單尚未核准，無法正式送出，請留在草稿狀態")
    from app.services import jobs

    # 用條件式 UPDATE（WHERE status='draft'）避免併發重複送出造成重複稽核紀錄；
    # 若 0 列更新，代表已被另一個請求搶先送出，直接回傳目前（已送出）狀態，不視為錯誤。
    changed = db.query(Jiaan1030ServiceFormDraft).filter(
        Jiaan1030ServiceFormDraft.id == draft.id,
        Jiaan1030ServiceFormDraft.status == "draft",
    ).update(
        {"status": "submitted", "submitted_at": jobs.utcnow(), "updated_by": user.id},
        synchronize_session="fetch",
    )
    db.refresh(draft)
    if changed == 0:
        return _draft_out(draft)
    audit.record(db, "jiaan1030_draft.submit", actor=user, target_type="jiaan1030_service_form_draft",
                 target_id=draft.id, meta={"form_code": draft.form_code, "status_to": "submitted"})
    db.commit()
    return _draft_out(draft)


# ── 表單範本核准（雙旗標） ──────────────────────────────────────────

@router.post("/jiaan1030/service-forms/{code}/approve")
def approve_form(
    code: str,
    body: ApproveFormBody,
    user: User = Depends(require_roles(*roles.APPROVERS)),
    db: Session = Depends(get_db),
) -> dict:
    form = _form_row(db, code)
    if form is None:
        raise _err(404, "not_found", "找不到表單範本")
    if body.schema_status is None and body.reviewed is None:
        raise _err(400, "no_change", "請明確指定要變更的狀態")
    if body.schema_status is not None:
        if body.schema_status not in ("draft_unverified", "verified_pending_approval", "approved"):
            raise _err(400, "invalid_schema_status", "schema_status 值不合法")
        result = db.execute(
            text("UPDATE jiaan1030_service_forms SET schema_status = :v WHERE code = :code"),
            {"v": body.schema_status, "code": code},
        )
        if result.rowcount != 1:
            raise _err(409, "update_conflict", "更新受影響列數不符預期")
        audit.record(db, "jiaan1030_form.approve", actor=user, target_type="jiaan1030_service_form",
                     target_id=code, meta={"form_code": code, "status_to": body.schema_status})
    if body.reviewed is not None:
        if body.reviewed and form["schema_status"] != "approved" and body.schema_status != "approved":
            raise _err(409, "schema_not_approved", "欄位內容尚未人工核對完成（schema_status != approved），不可設 reviewed=TRUE")
        result = db.execute(
            text("UPDATE jiaan1030_service_forms SET reviewed = :v WHERE code = :code"),
            {"v": body.reviewed, "code": code},
        )
        if result.rowcount != 1:
            raise _err(409, "update_conflict", "更新受影響列數不符預期")
        audit.record(db, "jiaan1030_form.approve", actor=user, target_type="jiaan1030_service_form",
                     target_id=code, meta={"form_code": code, "status_to": "reviewed" if body.reviewed else "unreviewed"})
    db.commit()
    return _form_row(db, code)
