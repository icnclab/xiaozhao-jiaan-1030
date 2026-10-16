"""治理指標：每一項都附分子、分母與白話定義，避免無分母的百分比。"""

from __future__ import annotations

import statistics
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Case, Document, DocumentVersion, Feedback, NotificationJob, QaItem
from app.services.documents import current_versions


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def compute_metrics(session: Session, org_id: uuid.UUID, facility_type: str, days: int) -> dict[str, Any]:
    """計算指定期間的治理指標。

    Args:
        session: ORM session。
        org_id: 機構。
        facility_type: 機構類型（知識庫涵蓋用）。
        days: 往回統計天數。

    Returns:
        指標字典。
    """
    tz = ZoneInfo(get_settings().tz_name)
    now = datetime.now(tz)
    since = now - timedelta(days=days)

    def count(stmt: Any) -> int:
        return int(session.scalar(stmt) or 0)

    total_q = count(select(func.count()).select_from(QaItem).where(QaItem.org_id == org_id, QaItem.created_at >= since))
    answered = count(select(func.count()).select_from(QaItem).where(
        QaItem.org_id == org_id, QaItem.created_at >= since, QaItem.outcome == "answered"))
    escalated = count(select(func.count()).select_from(QaItem).where(
        QaItem.org_id == org_id, QaItem.created_at >= since, QaItem.outcome.in_(["escalated", "escalation_failed"])))
    failed_case = count(select(func.count()).select_from(QaItem).where(
        QaItem.org_id == org_id, QaItem.created_at >= since, QaItem.outcome == "escalation_failed"))
    reasons = dict(session.execute(
        select(QaItem.escalation_reason, func.count()).where(
            QaItem.org_id == org_id, QaItem.created_at >= since, QaItem.escalation_reason.is_not(None))
        .group_by(QaItem.escalation_reason)).all())

    pending = count(select(func.count()).select_from(Case).where(Case.org_id == org_id, Case.status == "pending"))
    in_progress = count(select(func.count()).select_from(Case).where(Case.org_id == org_id,
                                                                     Case.status == "in_progress"))
    unassigned = count(select(func.count()).select_from(Case).where(
        Case.org_id == org_id, Case.status.in_(["pending", "in_progress"]), Case.assignee_id.is_(None)))
    created_cases = session.execute(select(Case.created_at, Case.first_replied_at).where(
        Case.org_id == org_id, Case.created_at >= since)).all()
    minutes = [(r.first_replied_at - r.created_at).total_seconds() / 60 for r in created_cases if r.first_replied_at]

    wrong = count(select(func.count()).select_from(Feedback).where(
        Feedback.org_id == org_id, Feedback.created_at >= since, Feedback.kind == "wrong"))
    helpful = count(select(func.count()).select_from(Feedback).where(
        Feedback.org_id == org_id, Feedback.created_at >= since, Feedback.kind == "helpful"))
    notif_failed = count(select(func.count()).select_from(NotificationJob).where(
        NotificationJob.org_id == org_id, NotificationJob.created_at >= since, NotificationJob.status == "failed"))
    notif_total = count(select(func.count()).select_from(NotificationJob).where(
        NotificationJob.org_id == org_id, NotificationJob.created_at >= since))

    version_ids = current_versions(session, org_id, facility_type, now.date())
    last_publish = session.scalar(select(func.max(DocumentVersion.published_at)).join(
        Document, Document.id == DocumentVersion.document_id).where(DocumentVersion.id.in_(version_ids))) \
        if version_ids else None

    return {
        "period": {"days": days, "from": since.isoformat(), "to": now.isoformat()},
        "refusal_rate": {
            "value": _ratio(escalated, total_q), "numerator": escalated, "denominator": total_q,
            "definition": "期間內轉督導（含建案失敗）的提問數 ÷ 期間內全部提問數",
            "by_reason": reasons,
        },
        "answered": {"numerator": answered, "denominator": total_q, "value": _ratio(answered, total_q),
                     "definition": "期間內附出處回答的提問數 ÷ 全部提問數"},
        "case_create_failed": {"count": failed_case, "definition": "期間內轉督導但建案失敗、需重試的提問數"},
        "backlog": {"pending": pending, "in_progress": in_progress, "unassigned": unassigned,
                    "definition": "目前（非期間）待處理、處理中與未指派的案件數"},
        "first_reply_minutes": {
            "median": round(statistics.median(minutes), 1) if minutes else None,
            "mean": round(statistics.fmean(minutes), 1) if minutes else None,
            "replied": len(minutes), "created": len(created_cases),
            "definition": "期間內建立且已回覆的案件，建案到第一次回覆的分鐘數；分母為已回覆案件數（未回覆者不計入）",
        },
        "feedback": {"wrong": wrong, "helpful": helpful, "answered": answered,
                     "wrong_rate": _ratio(wrong, answered),
                     "definition": "「回答有誤」標記數 ÷ 期間內附出處回答數（一人一答最多計一次）"},
        "notifications": {"failed": notif_failed, "total": notif_total,
                          "definition": "通知失敗數 ÷ 期間內通知工作數；accepted 只代表 LINE 平臺受理，不代表送達"},
        "knowledge_base": {"current_documents": len(version_ids),
                           "last_published_at": last_publish.isoformat() if last_publish else None},
        "note": "拒答比例高不代表系統差：知識庫涵蓋不足或問題涉及臨床判斷時，轉督導是正確行為。",
    }
