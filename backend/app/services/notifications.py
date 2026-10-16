"""通知工作：把「回覆已保存」「通知待送」「通知結果」分開記錄。

推播內容只放案件編號與 LIFF 連結；回覆全文留在系統內，照服員在 LIFF 查看。
`accepted` 代表 LINE 平臺受理，不代表送達。
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.line.client import get_line_client
from app.models import LineAccount, NotificationJob
from app.services import jobs


def liff_url(path: str) -> str:
    """LIFF 頁面連結由 PUBLIC_BASE_URL 組合；SDK 仍以 LIFF_ID 驗證登入。"""
    settings = get_settings()
    path = path.lstrip("/")
    return f"{settings.public_base_url.rstrip('/')}/liff/{path}"


def build_messages(notification: NotificationJob) -> list[dict[str, Any]]:
    """依通知種類組 LINE 訊息。"""
    payload = notification.payload
    kind = payload.get("kind")
    if kind == "case_reply":
        return [{
            "type": "text",
            "text": f"您送交的案件 {payload['case_number']} 督導已回覆。\n請點此查看：{liff_url('cases/' + payload['case_id'])}",
        }]
    if kind == "transcript_ready":
        return payload["messages"]
    if kind == "answer":
        return payload["messages"]
    raise ValueError(f"unknown notification kind {kind}")


def send(session: Session, notification_id: uuid.UUID) -> tuple[bool, bool]:
    """送出通知（worker 呼叫）。

    Args:
        session: ORM session（由呼叫端 commit）。
        notification_id: 通知 ID。

    Returns:
        (是否成功或已終結, 失敗時是否可重試)。
    """
    notification = session.get(NotificationJob, notification_id)
    if notification is None or notification.status in {"accepted", "skipped"}:
        return True, False
    account = session.scalar(select(LineAccount).where(LineAccount.user_id == notification.recipient_id))
    if account is None:
        notification.status, notification.last_error_code = "skipped", "no_line_account"
        return True, False
    if account.is_blocked:
        notification.status, notification.last_error_code = "skipped", "blocked"
        return True, False
    notification.status = "sending"
    notification.attempts += 1
    result = get_line_client(session).push(account.line_user_id, build_messages(notification),
                                           str(notification.retry_key))
    if result.accepted:
        notification.status = "accepted"
        notification.accepted_at = jobs.utcnow()
        notification.last_error_code = None
        notification.last_error = None
        return True, False
    notification.status = "failed"
    notification.last_error_code = result.error_code
    notification.last_error = f"HTTP {result.status_code}"
    return False, result.retryable


def retry(session: Session, notification: NotificationJob) -> NotificationJob:
    """手動重送（沿用同一 retry key，LINE 端不會重複送出已受理的請求）。"""
    if notification.status not in {"failed", "skipped"}:
        return notification
    notification.status = "queued"
    jobs.enqueue(session, "notify", {"notification_id": str(notification.id)},
                 f"notify:{notification.id}:manual{notification.attempts}")
    return notification
