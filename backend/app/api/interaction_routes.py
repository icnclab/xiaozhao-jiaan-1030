"""隔離服務互動：明確分組、機構與逐群組授權、唯讀歷程／技術資訊。"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, exists, and_, or_
from sqlalchemy.orm import Session
from app.auth import current_user, deny_not_found, require_roles
from app.db import get_db
from app.interaction_models import Interaction, HistoryGrant
from app.models import QaItem, Case, CaseEvent, CaseMessage, User, NotificationJob, Transcript, Category
from app.api.serializers import citations_out
from app.services import audit

router = APIRouter(prefix="/interactions", tags=["isolated interaction history"])

# 安全預設為關閉：只有嘉安確認「舊案受派居督可讀必要案件資料」的
# 書面規範、完成真實 PostgreSQL/API 驗證後，才可在受控部署版本中明確開啟。
# 這個開關僅擴充「案件業務權限」，永不授予問答／群組／逐字稿讀取權限。
LEGACY_ASSIGNEE_CASE_ACCESS_APPROVED = False

# Exact DB category name plus server-generated category header are both required.
# Never infer a complaint's sensitivity from user-supplied free text alone. If
# a category is renamed, historical reports fail closed instead of silently
# changing their access class. These two names must match the deployed catalog.
ROUTINE_QUICK_REPORT_CATEGORIES = ("服務性問題", "額外要求")


def routine_quick_report(db, case):
    """Only known, correctly classified routine reports may use assignee case scope."""
    if case.source != "quick_report" or not case.category_id:
        return False
    category = db.get(Category, case.category_id)
    return bool(category and category.org_id == case.org_id
                and category.name in ROUTINE_QUICK_REPORT_CATEGORIES
                and case.summary_masked.startswith(f"【{category.name}】\n"))


def routine_quick_report_sql():
    """SQL equivalent of routine_quick_report, used before list LIMIT and stats."""
    return and_(
        Case.source == "quick_report",
        or_(*(exists(select(Category.id).where(
            Category.id == Case.category_id,
            Category.org_id == Case.org_id,
            Category.name == label,
            Case.summary_masked.like(f"【{label}】\n%"),
        )) for label in ROUTINE_QUICK_REPORT_CATEGORIES)),
    )


def allowed(db, user, group):
    if group.org_id != user.org_id or not user.is_active:
        return False
    if user.role == "caregiver":
        return group.owner_id == user.id
    if user.role not in {"supervisor", "director"}:
        return False  # admin 名稱本身不授予私人內容權限
    if restricted_group(db, group):
        return False  # 尚未核准的申訴迴避／改派後查閱政策，不能由一般讀取授權繞過
    grant = db.scalar(select(HistoryGrant).where(HistoryGrant.interaction_id == group.id,
                                                HistoryGrant.viewer_id == user.id))
    approver = db.get(User, grant.approved_by) if grant else None
    return bool(grant and grant.read_approved and approver and approver.org_id == group.org_id
                and approver.is_active and approver.role in {"director", "supervisor"}
                and (user.role == "director" or grant.responsible))


def restricted_group(db, group):
    """缺少可靠申訴欄位，不用自由文字猜測；關聯分類回報全部保守隔離。

    改派或無法判定是否初次指派的歷程也不開放第三方。本人仍可查自己的資料。
    不修改案件／授權列，不自動擴張新受派者或保留舊受派者的查閱權。
    """
    related = select(Case).join(QaItem, Case.qa_item_id == QaItem.id).where(
        QaItem.conversation_id == group.id, QaItem.org_id == group.org_id,
        QaItem.user_id == group.owner_id, Case.org_id == group.org_id)
    for case in db.scalars(related):
        if case.source == "quick_report":
            return True
        for event in db.scalars(select(CaseEvent).where(CaseEvent.case_id == case.id,
                                                       CaseEvent.kind.in_(["assigned", "assign"]))):
            data = event.data or {}
            if "previous" not in data:
                if data.get("by") != "category_default":
                    return True
            elif data["previous"] and data["previous"] != data.get("assignee_id"):
                return True
    return False


def visible(db, user):
    groups = db.scalars(select(Interaction).where(Interaction.org_id == user.org_id)
                       .order_by(Interaction.created_at.desc(), Interaction.id.desc())).all()
    return [g for g in groups if allowed(db, user, g)]


def load(db, user, id, lock=False):
    stmt = select(Interaction).where(Interaction.id == id)
    group = db.scalar(stmt.with_for_update() if lock else stmt)
    if not group or not allowed(db, user, group):
        raise deny_not_found(db, user, "interaction", id)
    return group


def qas(db, g):
    return db.scalars(select(QaItem).where(QaItem.conversation_id == g.id,
        QaItem.org_id == g.org_id, QaItem.user_id == g.owner_id)
        .order_by(QaItem.created_at, QaItem.id)).all()


def grouped_qa_allowed(db, user, item):
    """舊單筆入口也不能因同機構或 admin 名稱越過新群組授權。"""
    group = db.get(Interaction, item.conversation_id)
    if item.org_id != user.org_id:
        return False
    return (item.user_id == user.id if group is None else
            (item.user_id == group.owner_id and item.org_id == group.org_id
                             and allowed(db, user, group))
            )


def _case_links_valid(db, case):
    """QA 與錄音必須真正屬於案件建立者及其機構；不能只靠外鍵識別碼。"""
    creator = db.get(User, case.created_by)
    if creator is None or creator.org_id != case.org_id:
        return False, None
    item = db.get(QaItem, case.qa_item_id) if case.qa_item_id else None
    if case.qa_item_id and not item:
        return False, item
    if item and (item.org_id != case.org_id or item.user_id != case.created_by):
        return False, item
    if case.transcript_id:
        tr = db.get(Transcript, case.transcript_id)
        if not tr or tr.org_id != case.org_id or tr.user_id != case.created_by:
            return False, item
    return True, item


def case_private_qa_allowed(db, user, case):
    """完整 QA、來源、逐字稿：本人或經批准的群組讀取授權，受派案件本身不構成授權。"""
    if not user.is_active or case.org_id != user.org_id:
        return False
    valid, item = _case_links_valid(db, case)
    return bool(valid and item and grouped_qa_allowed(db, user, item))


def case_allowed(db, user, case):
    """只判斷案件必要業務資料；絕不因此解鎖完整私人問答。"""
    if not user.is_active or case.org_id != user.org_id:
        return False
    valid, item = _case_links_valid(db, case)
    if not valid:
        return False
    if case.created_by == user.id:
        return not item or grouped_qa_allowed(db, user, item)
    if user.role != "supervisor":
        return False
    # Operational case details for a *current assigned* supervisor only.
    # No QA, citations or transcript are unlocked by this path.
    if case.assignee_id == user.id and routine_quick_report(db, case):
        return True
    group = db.get(Interaction, item.conversation_id) if item else None
    if group:
        # 新群組仍須經明確核准，包含申訴／改派的保守拒絕規則。
        return case_private_qa_allowed(db, user, case)
    # 未分組舊案：必須有書面政策開關 + 本人受派；快速分類回報在申訴政策
    # 未確認前仍維持預設拒絕。管理員不因技術角色取得業務／私人權限。
    return bool(LEGACY_ASSIGNEE_CASE_ACCESS_APPROVED
                and case.assignee_id == user.id
                and case.source in {"ai_escalation", "manual_escalation"})


def case_mutation_allowed(db, user, case):
    """案件處理必須為本人受派且有業務查閱權；不以歷程唯讀授權給予寫入權。"""
    return bool(user.role == "supervisor" and user.is_active
                and case.assignee_id == user.id and case_allowed(db, user, case))


def guard_assignment(db, case, target_id):
    """新群組的改派規則未核准：禁止改派／接手繞過；舊案件流程不變。"""
    item = db.get(QaItem, case.qa_item_id) if case.qa_item_id else None
    group = db.get(Interaction, item.conversation_id) if item else None
    if not group:
        return
    # Routine reports can be handled by their *existing* assignee even when
    # the linked private conversation has no grant. Reassignment is NOT allowed.
    if (routine_quick_report(db, case) and case.assignee_id == target_id
            and case.assignee_id is not None):
        target = db.get(User, target_id)
        if (target and target.org_id == case.org_id and target.is_active
                and target.role == "supervisor"):
            return
    target = db.get(User, target_id)
    if (case.assignee_id and case.assignee_id != target_id) or not target or not allowed(db, target, group):
        raise HTTPException(409, {"code": "history_assignment_policy_pending",
                                  "message": "此互動的改派與歷程查閱規則尚待確認，未變更指派"})


def visible_qa_ids(db, user):
    """在舊列表 LIMIT 前套用新群組權限；未分組舊資料維持原規則。"""
    ids = [g.id for g in visible(db, user)]
    grouped = select(Interaction.id)
    owned_groups = select(Interaction.id).where(Interaction.owner_id == QaItem.user_id,
                                               Interaction.org_id == QaItem.org_id).correlate(QaItem)
    return select(QaItem.id).where(QaItem.org_id == user.org_id,
        ((~QaItem.conversation_id.in_(grouped)) & (QaItem.user_id == user.id)) |
        (QaItem.conversation_id.in_(ids) & QaItem.conversation_id.in_(owned_groups)))


def visible_case_ids(db, user):
    """列表、統計及通知沿用同一查閱範圍；舊受派者須業務政策明確核准。"""
    ids = [g.id for g in visible(db, user)]
    scoped_qa = select(QaItem.id).where(QaItem.org_id == user.org_id,
        QaItem.user_id == Case.created_by, QaItem.conversation_id.in_(ids)).correlate(Case)
    tr_valid = (Case.transcript_id.is_(None) | exists(select(Transcript.id).where(
        Transcript.id == Case.transcript_id, Transcript.org_id == user.org_id,
        Transcript.user_id == Case.created_by)))
    owner = ((Case.created_by == user.id) &
             (Case.qa_item_id.is_(None) | Case.qa_item_id.in_(visible_qa_ids(db, user))))
    # A legitimate routine report remains actionable without granting its QA.
    # SQL filtering must match case_allowed() or list/detail will disagree.
    routine_assignee = False
    if user.role == "supervisor" and user.is_active:
        routine_assignee = and_(Case.assignee_id == user.id, routine_quick_report_sql())
    linked_qa_valid = or_(Case.qa_item_id.is_(None), exists(select(QaItem.id).where(
        QaItem.id == Case.qa_item_id, QaItem.org_id == Case.org_id,
        QaItem.user_id == Case.created_by)))
    creator_valid = exists(select(User.id).where(User.id == Case.created_by,
                                                User.org_id == Case.org_id))
    legacy_assignee = False
    if LEGACY_ASSIGNEE_CASE_ACCESS_APPROVED and user.role == "supervisor" and user.is_active:
        # 查詢的 QA 不屬於新群組；不可讓受派者繞過新群組／申訴授權。
        valid_legacy_qa = exists(select(QaItem.id).where(
            QaItem.id == Case.qa_item_id, QaItem.org_id == user.org_id,
            QaItem.user_id == Case.created_by,
            ~exists(select(Interaction.id).where(Interaction.id == QaItem.conversation_id))
        ))
        legacy_assignee = ((Case.assignee_id == user.id) &
            Case.source.in_(("ai_escalation", "manual_escalation")) &
            (Case.qa_item_id.is_(None) | valid_legacy_qa))
    return select(Case.id).where(Case.org_id == user.org_id, tr_valid,
        creator_valid, linked_qa_valid,
        owner | Case.qa_item_id.in_(scoped_qa) | routine_assignee | legacy_assignee)


def visible_notification_ids(db, user):
    return select(NotificationJob.id).where(NotificationJob.org_id == user.org_id,
        NotificationJob.case_id.in_(visible_case_ids(db, user)) |
        (NotificationJob.case_id.is_(None) & (NotificationJob.recipient_id == user.id)))


def linked_cases(db, g):
    return db.scalars(select(Case).join(QaItem, Case.qa_item_id == QaItem.id).where(
        QaItem.conversation_id == g.id, QaItem.org_id == g.org_id, QaItem.user_id == g.owner_id,
        Case.org_id == g.org_id, Case.created_by == g.owner_id).order_by(Case.created_at, Case.id)).all()


def brief(db, g):
    items, cases = qas(db, g), linked_cases(db, g)
    owner = db.get(User, g.owner_id)
    responsible = []
    for grant, viewer in db.execute(select(HistoryGrant, User).join(User, User.id == HistoryGrant.viewer_id)
        .where(HistoryGrant.interaction_id == g.id, HistoryGrant.responsible.is_(True),
               HistoryGrant.read_approved.is_(True), User.org_id == g.org_id,
               User.role == "supervisor", User.is_active.is_(True))):
        if allowed(db, viewer, g):
            responsible.append({"id": str(viewer.id), "name": viewer.display_name})
    return {"id": str(g.id), "reference": "SI-" + str(g.id), "topic": "服務互動（非正式照顧紀錄）",
        "owner_id": str(g.owner_id), "owner_name": owner.display_name if owner else "停用帳號",
        "responsible_supervisors": responsible, "created_at": g.created_at, "ended_at": g.ended_at,
        "question_count": len(items), "cases": [{"id": str(c.id), "number": c.number,
        "status": c.status, "assignee_id": str(c.assignee_id) if c.assignee_id else None} for c in cases],
        "latest_status": cases[-1].status if cases else "no_case"}


class StartIn(BaseModel):
    client_request_id: str = Field(min_length=8, max_length=64)


@router.post("")
def start(body: StartIn, user: User = Depends(require_roles("caregiver")), db: Session = Depends(get_db)):
    group = db.scalar(select(Interaction).where(Interaction.owner_id == user.id,
                                               Interaction.start_request_id == body.client_request_id))
    if group and group.org_id != user.org_id:
        raise deny_not_found(db, user, "interaction", group.id)
    if not group:
        group = Interaction(org_id=user.org_id, owner_id=user.id, start_request_id=body.client_request_id)
        db.add(group)
        db.flush()
        audit.record(db, "interaction.start", actor=user, target_type="interaction", target_id=group.id)
        db.commit()
    return brief(db, group)


@router.get("")
def listing(owner_id: uuid.UUID | None = None, supervisor_id: uuid.UUID | None = None,
            status: str | None = None, after: datetime | None = None, before: datetime | None = None,
            user: User = Depends(require_roles("caregiver", "supervisor", "director")), db: Session = Depends(get_db)):
    if status and status not in {"pending", "in_progress", "replied", "closed", "no_case"}:
        raise HTTPException(422, "invalid status")
    if (after and after.tzinfo is None) or (before and before.tzinfo is None):
        raise HTTPException(422, "timezone required")
    rows = []
    owners, supervisors = {}, {}
    for g in visible(db, user):
        row = brief(db, g)
        owners[row["owner_id"]] = row["owner_name"]
        for viewer in row["responsible_supervisors"]:
            supervisors[viewer["id"]] = viewer["name"]
        for case in row["cases"]:
            assignee = db.get(User, uuid.UUID(case["assignee_id"])) if case["assignee_id"] else None
            if assignee and assignee.org_id == user.org_id and assignee.role == "supervisor" and assignee.is_active:
                supervisors[str(assignee.id)] = assignee.display_name
        if owner_id and g.owner_id != owner_id or after and g.created_at < after or before and g.created_at > before:
            continue
        if supervisor_id and not (any(c["assignee_id"] == str(supervisor_id) for c in row["cases"])
            or any(v["id"] == str(supervisor_id) for v in row["responsible_supervisors"])):
            continue
        if status and (not any(c["status"] == status for c in row["cases"]) if status != "no_case" else bool(row["cases"])):
            continue
        rows.append(row)
    counts = {}
    for row in rows:
        for case in row["cases"]:
            key = case["assignee_id"] or "unassigned"
            counts.setdefault(key, {"total": 0, "pending": 0, "in_progress": 0, "replied": 0, "closed": 0})
            counts[key]["total"] += 1
            if case["status"] in counts[key]:
                counts[key][case["status"]] += 1
    audit.record(db, "interaction.list", actor=user, meta={"count": len(rows)})
    db.commit()
    return {"items": rows, "total": len(rows), "by_supervisor": counts,
            "filters": {"owners": [{"id": k, "name": v} for k, v in owners.items()],
                        "supervisors": [{"id": k, "name": v} for k, v in supervisors.items()]}}


@router.get("/legacy")
def legacy(user: User = Depends(require_roles("caregiver")), db: Session = Depends(get_db)):
    # 舊資料逐題展示，絕不按日期或人員自動合併。
    rows = db.scalars(select(QaItem).where(QaItem.org_id == user.org_id, QaItem.user_id == user.id,
        ~exists(select(Interaction.id).where(Interaction.id == QaItem.conversation_id)))
        .order_by(QaItem.created_at.desc(), QaItem.id).limit(100)).all()
    audit.record(db, "interaction.legacy", actor=user, meta={"count": len(rows)})
    db.commit()
    return [{"id": str(q.id), "created_at": q.created_at, "question_masked": q.question_masked,
             "outcome": q.outcome} for q in rows]


@router.get("/technical")
def technical(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    rows = []
    for g in db.scalars(select(Interaction).where(Interaction.org_id == user.org_id)):
        items = qas(db, g)
        rows.append({"id": str(g.id), "reference": "SI-" + str(g.id), "question_count": len(items),
                     "case_count": len(linked_cases(db, g)), "ended": g.ended_at is not None,
                     "qa_ids": [str(q.id) for q in items],
                     "outcomes": [q.outcome for q in items]})
    audit.record(db, "interaction.technical", actor=user, meta={"count": len(rows)})
    db.commit()
    return rows



# ===== Consent-driven private history grant workflow ========================
# Existing integration tests can seed grants directly, but real caregivers now
# have an API to request them. Approval never follows case assignment alone.

class AccessRequestIn(BaseModel):
    viewer_id: uuid.UUID


@router.post("/{id}/access-requests")
def request_private_access(id: uuid.UUID, body: AccessRequestIn,
                           user: User = Depends(require_roles("caregiver")),
                           db: Session = Depends(get_db)):
    """Owner nominates one viewer; does NOT immediately disclose any content."""
    group = load(db, user, id)
    if group.owner_id != user.id:
        raise deny_not_found(db, user, "interaction", id)
    viewer = db.get(User, body.viewer_id)
    if (not viewer or not viewer.is_active or viewer.org_id != group.org_id
            or viewer.role not in {"supervisor", "director"}):
        raise HTTPException(422, {"code": "invalid_viewer", "message": "只可申請同機構督導／主任"})
    if restricted_group(db, group):
        raise HTTPException(409, {"code": "sensitive_history_policy_pending",
                                  "message": "此互動涉及受限制案件，不開放完整歷程"})
    grant = db.scalar(select(HistoryGrant).where(HistoryGrant.interaction_id == group.id,
                                               HistoryGrant.viewer_id == viewer.id).with_for_update())
    if grant and grant.read_approved:
        return {"interaction_id": str(group.id), "viewer_id": str(viewer.id), "status": "approved"}
    if not grant:
        grant = HistoryGrant(interaction_id=group.id, viewer_id=viewer.id,
                             approved_by=user.id, read_approved=False,
                             responsible=viewer.role == "supervisor")
        db.add(grant)
    else:
        grant.approved_by = user.id  # fresh consent required after prior denial
        grant.responsible = viewer.role == "supervisor"
    audit.record(db, "interaction.access_request", actor=user,
                 target_type="interaction", target_id=group.id,
                 meta={"viewer_id": str(viewer.id)})
    db.commit()
    return {"interaction_id": str(group.id), "viewer_id": str(viewer.id), "status": "pending"}


@router.get("/access-requests")
def list_access_requests(user: User = Depends(require_roles("director")),
                         db: Session = Depends(get_db)):
    """Director sees pending authorization metadata, not conversation content."""
    rows = db.execute(select(HistoryGrant, Interaction).join(
        Interaction, Interaction.id == HistoryGrant.interaction_id).where(
        Interaction.org_id == user.org_id, HistoryGrant.read_approved.is_(False),
        HistoryGrant.approved_by == Interaction.owner_id)).all()
    return [{"interaction_id": str(g.id), "viewer_id": str(gr.viewer_id),
             "owner_id": str(g.owner_id)} for gr, g in rows
            if not restricted_group(db, g)]


@router.post("/{id}/grants/{viewer_id}/approve")
def approve_private_access(id: uuid.UUID, viewer_id: uuid.UUID,
                           user: User = Depends(require_roles("director")),
                           db: Session = Depends(get_db)):
    """Director approves only an explicit request from the interaction owner."""
    group = db.get(Interaction, id)
    if not group or group.org_id != user.org_id:
        raise deny_not_found(db, user, "interaction", id)
    if restricted_group(db, group):
        raise HTTPException(409, {"code": "sensitive_history_policy_pending"})
    grant = db.scalar(select(HistoryGrant).where(HistoryGrant.interaction_id == id,
                                               HistoryGrant.viewer_id == viewer_id).with_for_update())
    viewer = db.get(User, viewer_id)
    if (not grant or grant.read_approved or grant.approved_by != group.owner_id
            or not viewer or viewer.org_id != group.org_id or not viewer.is_active
            or viewer.role not in {"supervisor", "director"}):
        raise HTTPException(409, {"code": "no_valid_owner_request"})
    grant.read_approved = True
    grant.responsible = viewer.role == "supervisor"
    grant.approved_by = user.id
    audit.record(db, "interaction.access_approve", actor=user,
                 target_type="interaction", target_id=group.id,
                 meta={"viewer_id": str(viewer_id)})
    db.commit()
    return {"interaction_id": str(id), "viewer_id": str(viewer_id), "status": "approved"}


@router.delete("/{id}/grants/{viewer_id}", status_code=204)
def revoke_private_access(id: uuid.UUID, viewer_id: uuid.UUID,
                          user: User = Depends(require_roles("caregiver", "director")),
                          db: Session = Depends(get_db)):
    """Owner or director removes grant; access is revoked on the next request."""
    group = db.get(Interaction, id)
    if (not group or group.org_id != user.org_id
            or (user.role == "caregiver" and group.owner_id != user.id)):
        raise deny_not_found(db, user, "interaction", id)
    grant = db.scalar(select(HistoryGrant).where(HistoryGrant.interaction_id == id,
                                               HistoryGrant.viewer_id == viewer_id).with_for_update())
    if not grant:
        raise deny_not_found(db, user, "history_grant", viewer_id)
    db.delete(grant)
    audit.record(db, "interaction.access_revoke", actor=user,
                 target_type="interaction", target_id=group.id,
                 meta={"viewer_id": str(viewer_id)})
    db.commit()
    return Response(status_code=204)


# Minimal org-scoped metadata APIs for consent UI; never return conversation text.
@router.get("/eligible-viewers")
def eligible_viewers(user: User = Depends(require_roles("caregiver")),
                     db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.org_id == user.org_id,
        User.is_active.is_(True), User.role.in_(["supervisor", "director"]))
        .order_by(User.display_name, User.id)).all()
    return [{"id": str(row.id), "display_name": row.display_name,
             "role": row.role} for row in rows]


@router.get("/access-grants")
def list_access_grants(user: User = Depends(require_roles("caregiver", "director")),
                       db: Session = Depends(get_db)):
    """Only minimal authorization metadata. Caregivers see their own groups;
    directors see same-organization grants for revocation oversight."""
    stmt = (select(HistoryGrant, Interaction)
        .join(Interaction, Interaction.id == HistoryGrant.interaction_id)
        .where(Interaction.org_id == user.org_id))
    if user.role == "caregiver":
        stmt = stmt.where(Interaction.owner_id == user.id)
    rows = db.execute(stmt.order_by(HistoryGrant.created_at.desc(), HistoryGrant.id.desc())
                      .limit(500)).all()
    result = []
    for grant, group in rows:
        viewer = db.get(User, grant.viewer_id)
        owner = db.get(User, group.owner_id)
        result.append({"interaction_id": str(group.id),
                       "viewer_id": str(grant.viewer_id),
                       "viewer_name": viewer.display_name if viewer and viewer.org_id == user.org_id else "已停用帳號",
                       "viewer_role": viewer.role if viewer and viewer.org_id == user.org_id else "unknown",
                       "owner_name": owner.display_name if owner and owner.org_id == user.org_id else "已停用帳號",
                       "status": "approved" if grant.read_approved else "pending"})
    return result


@router.get("/{id}")
def detail(id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = load(db, user, id)
    timeline = []
    for q in qas(db, g):
        timeline.append({"kind": "qa", "id": str(q.id), "at": q.created_at,
            "source": q.source, "question": q.question_masked, "answer": q.answer_text,
            "outcome": q.outcome, "reason": q.escalation_reason,
            "checks": {k: v for k, v in q.checks.items() if k in {"risk", "risk_level", "refusal_reason"}},
            "citations": [{k: c[k] for k in ("id", "document_title", "locator", "version_label", "excerpt")}
                          for c in citations_out(db, q.id)], "submitter_id": str(q.user_id)})
    for c in linked_cases(db, g):
        timeline.append({"kind": "case", "id": str(c.id), "qa_id": str(c.qa_item_id),
            "number": c.number, "status": c.status, "at": c.created_at})
        for e in db.scalars(select(CaseEvent).where(CaseEvent.case_id == c.id)):
            # 原 data 不直接外送，僅允許同機構操作者與受派者識別碼。
            assignee = e.data.get("assignee_id") if e.data else None
            try:
                target = db.get(User, uuid.UUID(assignee)) if assignee else None
            except (ValueError, TypeError):
                target = None
            timeline.append({"kind": "event", "id": str(e.id), "case_id": str(c.id), "at": e.created_at,
                "action": e.kind, "from_status": e.from_status, "to_status": e.to_status,
                "actor_id": str(e.actor_id) if e.actor_id else None,
                "assignee_id": str(target.id) if target and target.org_id == g.org_id else None})
        for m in db.scalars(select(CaseMessage).where(CaseMessage.case_id == c.id)):
            timeline.append({"kind": "reply" if m.author_role == "supervisor" else "supplement",
                "id": str(m.id), "case_id": str(c.id), "at": m.created_at, "body": m.body,
                "author_role": m.author_role, "author_id": str(m.author_id)})
    priority = {"qa": 0, "case": 1, "event": 2, "reply": 3, "supplement": 3}
    timeline.sort(key=lambda e: (e["at"], priority[e["kind"]], e["id"]))
    audit.record(db, "interaction.read", actor=user, target_type="interaction", target_id=g.id)
    db.commit()
    return {**brief(db, g), "timeline": timeline, "can_ask": user.id == g.owner_id and g.ended_at is None}


@router.post("/{id}/end")
def end(id: uuid.UUID, user: User = Depends(require_roles("caregiver")), db: Session = Depends(get_db)):
    g = load(db, user, id, lock=True)
    if not g.ended_at:
        g.ended_at = datetime.now(timezone.utc)
        audit.record(db, "interaction.end", actor=user, target_type="interaction", target_id=id)
        db.commit()
    return brief(db, g)


def validate_ask(db, user, conversation_id, request_id):
    """Validate a managed group and report whether it already has Context.

    ``None`` means a legacy standalone conversation UUID, ``False`` means a
    managed Interaction with no prior QA, and ``True`` means Context exists.
    """
    g = db.scalar(select(Interaction).where(Interaction.id == conversation_id).with_for_update())
    if not g:
        return None
    if g.owner_id != user.id or g.org_id != user.org_id or user.role != "caregiver":
        raise deny_not_found(db, user, "interaction", conversation_id)
    previous = db.scalar(select(QaItem).where(
        QaItem.user_id == user.id,
        QaItem.client_request_id == request_id,
    ))
    if previous and previous.conversation_id != g.id:
        raise HTTPException(409, "request belongs to another interaction")
    if g.ended_at and not previous:
        raise HTTPException(409, "interaction ended")
    return bool(db.scalar(select(exists(select(QaItem.id).where(
        QaItem.conversation_id == g.id,
        QaItem.user_id == user.id,
        QaItem.org_id == user.org_id,
    )))))


def ensure_ask_interaction(db, user, conversation_id, request_id):
    """Create a caregiver's first group or validate an explicit continuation.

    The first request's idempotency key is also the start key.  A request that
    omits ``conversation_id`` can therefore never inherit another thread.
    """
    if conversation_id is not None:
        context_exists = validate_ask(db, user, conversation_id, request_id)
        return conversation_id, context_exists is not False
    if user.role != "caregiver":
        return None, False
    group = db.scalar(select(Interaction).where(
        Interaction.owner_id == user.id,
        Interaction.start_request_id == request_id,
    ).with_for_update())
    if group is not None:
        if group.org_id != user.org_id:
            raise deny_not_found(db, user, "interaction", group.id)
    else:
        group = Interaction(org_id=user.org_id, owner_id=user.id, start_request_id=request_id)
        db.add(group)
        db.flush()
    return group.id, False
