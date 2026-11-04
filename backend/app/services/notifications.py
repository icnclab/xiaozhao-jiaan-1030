"""通知工作：把「回覆已保存」「通知待送」「通知結果」分開記錄。

推播內容只放案件編號與 LIFF 連結；回覆全文留在系統內，照服員在 LIFF 查看。
`accepted` 代表 LINE 平臺受理，不代表送達。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.line.client import get_line_client
from app.models import LineAccount, NotificationJob
from app.services import jobs

# 既有 7 種緊急分類代碼的中文顯示名稱（與 jiaan1030_emergency_routes.CATEGORIES 對應，
# 僅供通知文字顯示用，不是新分類、不是自由文字，不含個案內容）。
EMERGENCY_CATEGORY_LABELS = {
    'fall': '跌倒', 'violence': '暴力／受威脅', 'injury': '傷口／受傷',
    'unresponsive': '昏倒／意識異常', 'traffic': '車禍', 'self_harm': '自傷風險', 'other': '重大緊急事件',
}


def short_incident_id(value: uuid.UUID) -> str:
    """與前端 emergency-ui 的 shortIncidentId() 一致，方便居督對照畫面上的通報卡片。"""
    return '#' + str(value)[:8].upper()


def liff_url(path: str) -> str:
    """LIFF 頁面連結由 PUBLIC_BASE_URL 組合；SDK 仍以 LIFF_ID 驗證登入。"""
    settings = get_settings()
    path = path.lstrip("/")
    return f"{settings.public_base_url.rstrip('/')}/liff/{path}"


def build_messages(notification: NotificationJob) -> list[dict[str, Any]]:
    """依通知種類組 LINE 訊息。"""
    payload = notification.payload
    kind = payload.get("kind")
    if kind == "jiaan_emergency_alert":
        # Never embed user-supplied incident descriptions or resident information in LINE.
        emergency_id = str(payload.get("emergency_id", ""))
        stage = payload.get("stage")
        try:
            parsed_id = uuid.UUID(emergency_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("invalid emergency notification ID") from exc
        if stage not in {"new", "unacknowledged_60s", "unacknowledged_180s"}:
            raise ValueError("invalid emergency notification stage")
        stage_text = {
            "new": "有新的緊急通報待確認",
            "unacknowledged_60s": "緊急通報逾一分鐘尚未接手，請立即確認",
            "unacknowledged_180s": "緊急通報逾三分鐘尚未接手，請依機構應變流程升級處理",
        }[stage]
        url = f"{get_settings().public_base_url.rstrip('/')}/api/jiaan1030/emergency-ui"
        category_label = EMERGENCY_CATEGORY_LABELS.get(payload.get("category"), "緊急事件")
        created_raw = payload.get("incident_created_at")
        created_text = ""
        if created_raw:
            try:
                created_local = datetime.fromisoformat(created_raw).astimezone(ZoneInfo(get_settings().tz_name))
                created_text = f"\n建立時間：{created_local.strftime('%Y-%m-%d %H:%M')}"
            except ValueError:
                created_text = ""
        return [{"type": "text", "text": (
            f"【小照緊急通報】{stage_text}。\n"
            f"事件類別：{category_label}{created_text}\n"
            "請立即依機構緊急流程確認；遇到立即危及生命情況請撥打 119。\n"
            f"查看並接手：{url}\n通報編號：{short_incident_id(parsed_id)}\n"
            "本訊息僅表示通知已發起，並非事件已接手。"
        )}]
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
    if notification.payload.get("kind") == "jiaan_emergency_alert":
        # Fail closed even for jobs queued before the feature flag was disabled.
        # The flag must be enabled in the ACTUAL worker process, not only the shell.
        from app.services.jiaan_emergency_dispatch import is_enabled
        if not is_enabled():
            # Never send a queued emergency alert after the feature is disabled.
            # Treat old queued alerts as skipped, not silently pending forever.
            notification.status, notification.last_error_code = "skipped", "feature_disabled"
            return True, False
        # Prevent queued alerts from sending after acknowledgement/resolution.
        incident_id = notification.payload.get("emergency_id")
        stage = notification.payload.get("stage")
        try:
            parsed_id = uuid.UUID(str(incident_id))
        except (TypeError, ValueError, AttributeError):
            notification.status, notification.last_error_code = "skipped", "invalid_incident"
            return True, False
        from sqlalchemy import text
        row = session.execute(text("""SELECT status, created_at FROM public.jiaan1030_emergencies
              WHERE id=:eid AND org_id=:org FOR SHARE"""),
              {"eid": parsed_id, "org": notification.org_id}).mappings().first()
        if row is None or row["status"] != "open":
            notification.status, notification.last_error_code = "skipped", "incident_not_open"
            return True, False
        from datetime import datetime, timezone
        age = (datetime.now(timezone.utc) - row["created_at"]).total_seconds()
        required_age = {"new": 0, "unacknowledged_60s": 60, "unacknowledged_180s": 180}.get(stage)
        if required_age is None:
            notification.status, notification.last_error_code = "skipped", "invalid_stage"
            return True, False
        if age < required_age:
            # This should not happen with scheduled sweeps. If it does, retry
            # instead of permanently losing a not-yet-due alert.
            return False, True
        # Final recipient check: active manager, same organization, matching stage.
        from app.models import User
        permitted = ("director", "admin") if stage == "unacknowledged_180s" else ("supervisor",)
        recipient = session.get(User, notification.recipient_id)
        if (not recipient or not recipient.is_active or recipient.org_id != notification.org_id
                or recipient.role not in permitted):
            notification.status, notification.last_error_code = "skipped", "recipient_not_authorized"
            return True, False
    account = session.scalar(select(LineAccount).where(LineAccount.user_id == notification.recipient_id))
    if account is None or account.linked_at is None:
        # A valid binding is mandatory at SEND time, not only at enqueue time.
        notification.status, notification.last_error_code = "skipped", "no_active_line_binding"
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
