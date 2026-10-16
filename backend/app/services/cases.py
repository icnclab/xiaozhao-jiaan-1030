"""督導案件：建案（冪等）、指派、接手、回覆（同一交易寫入通知工作）、結案。"""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Case, CaseEvent, CaseMessage, Category, LineAccount, NotificationJob, User
from app.services import audit, jobs
from app.services.deid import deidentify

STATUSES = ("pending", "in_progress", "replied", "closed")
TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in_progress", "replied", "closed"},
    "in_progress": {"in_progress", "replied", "closed"},
    "replied": {"in_progress", "closed"},
    "closed": set(),
}
STATUS_LABELS = {"pending": "待處理", "in_progress": "處理中", "replied": "已回覆", "closed": "已結案"}
SOURCE_LABELS = {"ai_escalation": "AI 轉人工", "manual_escalation": "照服員送交", "quick_report": "分類回報"}


class CaseError(Exception):
    """案件操作錯誤。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# 測試用故障注入：設為例外時，建案會拋出（驗證「建案失敗不顯示已轉交」）
FAULT_INJECTION: Exception | None = None


def _next_number(session: Session) -> str:
    seq = session.execute(text("SELECT nextval('case_number_seq')")).scalar_one()
    today = datetime.now(ZoneInfo(get_settings().tz_name)).strftime("%Y%m%d")
    return f"C-{today}-{seq:05d}"


def _transition(case: Case, to_status: str) -> str:
    if to_status not in TRANSITIONS[case.status]:
        raise CaseError("invalid_transition", f"案件目前為「{STATUS_LABELS[case.status]}」，不能改為「{STATUS_LABELS[to_status]}」")
    from_status, case.status = case.status, to_status
    return from_status


def resolve_assignee(session: Session, org_id: uuid.UUID, category_id: uuid.UUID | None) -> uuid.UUID | None:
    """依分類預設督導決定指派對象（須為同機構、啟用中的督導）。"""
    if category_id is None:
        return None
    category = session.get(Category, category_id)
    if category is None or category.org_id != org_id or category.default_assignee_id is None:
        return None
    assignee = session.get(User, category.default_assignee_id)
    if assignee and assignee.is_active and assignee.org_id == org_id and assignee.role in {"supervisor", "admin"}:
        return assignee.id
    return None


def create_case(
    session: Session,
    creator: User,
    *,
    source: str,
    summary_masked: str,
    reason: str,
    client_request_id: str,
    category_id: uuid.UUID | None = None,
    qa_item_id: uuid.UUID | None = None,
    transcript_id: uuid.UUID | None = None,
) -> tuple[Case, bool]:
    """建立案件；同一建立者＋client_request_id 重送時回傳既有案件。

    在 savepoint 內執行，失敗不會汙染外層交易（外層仍能保存問答與失敗狀態）。

    Args:
        session: ORM session。
        creator: 建立者（照服員）。
        source: ai_escalation、manual_escalation、quick_report。
        summary_masked: 遮罩後摘要。
        reason: 轉交原因。
        client_request_id: 冪等鍵。
        category_id: 分類。
        qa_item_id: 相關問答。
        transcript_id: 相關轉錄。

    Returns:
        (案件, 是否新建)。

    Raises:
        CaseError: 參數不合法。
        Exception: 資料庫錯誤（由呼叫端決定如何呈現）。
    """
    existing = session.scalar(
        select(Case).where(Case.created_by == creator.id, Case.client_request_id == client_request_id)
    )
    if existing:
        return existing, False
    if category_id is not None:
        category = session.get(Category, category_id)
        if category is None or category.org_id != creator.org_id or not category.is_active:
            raise CaseError("invalid_category", "分類不存在或已停用")
    with session.begin_nested():
        if FAULT_INJECTION is not None:
            raise FAULT_INJECTION
        assignee_id = resolve_assignee(session, creator.org_id, category_id)
        case = Case(
            org_id=creator.org_id,
            number=_next_number(session),
            category_id=category_id,
            created_by=creator.id,
            client_request_id=client_request_id,
            source=source,
            qa_item_id=qa_item_id,
            transcript_id=transcript_id,
            summary_masked=summary_masked[:4000],
            reason=reason[:200],
            status="pending",
            assignee_id=assignee_id,
        )
        session.add(case)
        session.flush()
        session.add(CaseEvent(case_id=case.id, actor_id=creator.id, kind="created", to_status="pending",
                              data={"source": source}))
        if assignee_id:
            session.add(CaseEvent(case_id=case.id, actor_id=None, kind="assigned", from_status="pending",
                                  to_status="pending", data={"assignee_id": str(assignee_id), "by": "category_default"}))
        audit.record(session, "case.create", actor=creator, target_type="case", target_id=case.id,
                     meta={"source": source, "assigned": bool(assignee_id)})
    return case, True


def assign(session: Session, actor: User, case: Case, assignee_id: uuid.UUID) -> Case:
    """指派／改派督導。"""
    assignee = session.get(User, assignee_id)
    if assignee is None or assignee.org_id != case.org_id or assignee.role not in {"supervisor", "admin"}:
        raise CaseError("invalid_assignee", "指派對象必須是同機構的督導")
    if case.status == "closed":
        raise CaseError("invalid_transition", "已結案的案件不能改派")
    previous = case.assignee_id
    case.assignee_id = assignee_id
    session.add(CaseEvent(case_id=case.id, actor_id=actor.id, kind="assigned", from_status=case.status,
                          to_status=case.status, data={"assignee_id": str(assignee_id),
                                                       "previous": str(previous) if previous else None}))
    audit.record(session, "case.assign", actor=actor, target_type="case", target_id=case.id)
    return case


def take(session: Session, actor: User, case: Case) -> Case:
    """督導接手：狀態改為處理中，指派給自己。"""
    from_status = _transition(case, "in_progress")
    case.assignee_id = actor.id
    session.add(CaseEvent(case_id=case.id, actor_id=actor.id, kind="taken", from_status=from_status,
                          to_status="in_progress"))
    audit.record(session, "case.take", actor=actor, target_type="case", target_id=case.id)
    return case


def reply(session: Session, actor: User, case: Case, body: str, client_request_id: str) -> tuple[CaseMessage, NotificationJob]:
    """督導回覆：回覆、歷程、通知工作在同一交易寫入；通知失敗不會丟失回覆。

    Args:
        session: ORM session（由呼叫端 commit）。
        actor: 督導。
        case: 案件。
        body: 回覆內容。
        client_request_id: 冪等鍵（重複點擊不重複回覆）。

    Returns:
        (回覆訊息, 通知工作)。
    """
    body = body.strip()
    if not body:
        raise CaseError("empty", "回覆內容不可空白")
    existing = session.scalar(
        select(CaseMessage).where(CaseMessage.author_id == actor.id, CaseMessage.client_request_id == client_request_id)
    )
    if existing:
        notification = session.scalar(
            select(NotificationJob).where(NotificationJob.source_type == "case_message",
                                          NotificationJob.source_id == existing.id)
        )
        assert notification is not None
        return existing, notification
    from_status = _transition(case, "replied")
    message = CaseMessage(case_id=case.id, author_id=actor.id, author_role=actor.role, body=body[:4000],
                          client_request_id=client_request_id)
    session.add(message)
    session.flush()
    if case.first_replied_at is None:
        case.first_replied_at = jobs.utcnow()
    if case.assignee_id is None:
        case.assignee_id = actor.id
    session.add(CaseEvent(case_id=case.id, actor_id=actor.id, kind="replied", from_status=from_status,
                          to_status="replied", data={"message_id": str(message.id)}))
    notification = queue_case_notification(session, case, message)
    audit.record(session, "case.reply", actor=actor, target_type="case", target_id=case.id,
                 meta={"notification_status": notification.status})
    return message, notification


def queue_case_notification(session: Session, case: Case, message: CaseMessage) -> NotificationJob:
    """為案件回覆建立通知工作。推播內容只放案件編號與 LIFF 連結，回覆全文留在系統內。"""
    account = session.scalar(select(LineAccount).where(LineAccount.user_id == case.created_by))
    if account is None:
        status, error_code = "skipped", "no_line_account"
    elif account.is_blocked:
        status, error_code = "skipped", "blocked"
    else:
        status, error_code = "queued", None
    notification = NotificationJob(
        org_id=case.org_id,
        recipient_id=case.created_by,
        case_id=case.id,
        source_type="case_message",
        source_id=message.id,
        channel="line",
        status=status,
        last_error_code=error_code,
        payload={"kind": "case_reply", "case_id": str(case.id), "case_number": case.number},
    )
    session.add(notification)
    session.flush()
    if status == "queued":
        jobs.enqueue(session, "notify", {"notification_id": str(notification.id)}, f"notify:{notification.id}")
    return notification


def caregiver_message(session: Session, actor: User, case: Case, body: str, client_request_id: str) -> CaseMessage:
    """照服員補充說明（遮罩後保存）；已回覆的案件會回到處理中。"""
    if case.created_by != actor.id:
        raise CaseError("forbidden", "只能補充自己的案件")
    if case.status == "closed":
        raise CaseError("invalid_transition", "已結案的案件不能補充")
    existing = session.scalar(
        select(CaseMessage).where(CaseMessage.author_id == actor.id, CaseMessage.client_request_id == client_request_id)
    )
    if existing:
        return existing
    masked = deidentify(body.strip()).text
    if not masked:
        raise CaseError("empty", "內容不可空白")
    message = CaseMessage(case_id=case.id, author_id=actor.id, author_role=actor.role, body=masked[:4000],
                          client_request_id=client_request_id)
    session.add(message)
    from_status = case.status
    if case.status == "replied":
        _transition(case, "in_progress")
    session.add(CaseEvent(case_id=case.id, actor_id=actor.id, kind="caregiver_message", from_status=from_status,
                          to_status=case.status))
    audit.record(session, "case.caregiver_message", actor=actor, target_type="case", target_id=case.id)
    return message


def close(session: Session, actor: User, case: Case, reason: str) -> Case:
    """結案（須附理由）。"""
    if not reason.strip():
        raise CaseError("empty", "請填寫結案理由")
    from_status = _transition(case, "closed")
    case.closed_at = jobs.utcnow()
    session.add(CaseEvent(case_id=case.id, actor_id=actor.id, kind="closed", from_status=from_status,
                          to_status="closed", data={"reason": reason.strip()[:200]}))
    audit.record(session, "case.close", actor=actor, target_type="case", target_id=case.id)
    return case


def is_unique_violation(exc: Exception) -> bool:
    """是否為唯一性衝突（併發重送時的保險）。"""
    return isinstance(exc, IntegrityError)
