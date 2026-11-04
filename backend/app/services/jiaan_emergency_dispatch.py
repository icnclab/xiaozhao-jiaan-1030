"""Opt-in, idempotent emergency LINE notification staging.

Default disabled. Does not claim delivery. Uses existing notify worker queue.
"""
from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import text, select
from sqlalchemy.orm import Session
from app.models import User, LineAccount, NotificationJob
from app.services import jobs

log = logging.getLogger(__name__)
STAGES = (("new", 0, ("supervisor",)),
          ("unacknowledged_60s", 60, ("supervisor",)),
          ("unacknowledged_180s", 180, ("director", "admin")))


def is_enabled() -> bool:
    return os.environ.get("JIAAN_EMERGENCY_LINE_DISPATCH", "off").strip().lower() == "on"


def sweep(session: Session, *, now: datetime | None = None) -> int:
    """Enqueue due stages for *bound* active managers, atomically under advisory lock.

    Caller must commit; on any failure it must rollback. Never includes resident data.
    """
    if not is_enabled():
        return 0
    now = now or datetime.now(timezone.utc)
    # Serializes sweep workers within one transaction and makes re-runs idempotent.
    acquired = session.execute(text("SELECT pg_try_advisory_xact_lock(16430102, 20261102) ")).scalar_one()
    if not acquired:
        return 0
    items = session.execute(text("""SELECT id, org_id, category, created_at
        FROM public.jiaan1030_emergencies
        WHERE status='open' AND created_at <= :now
        ORDER BY created_at LIMIT 100"""), {'now': now}).mappings().all()
    created = 0
    for incident in items:
        age = max(0, (now - incident['created_at']).total_seconds())
        for stage, threshold, roles in STAGES:
            if age < threshold:
                continue
            users = session.scalars(select(User).join(LineAccount, LineAccount.user_id == User.id).where(
                User.org_id == incident['org_id'], User.is_active.is_(True),
                User.role.in_(roles), LineAccount.linked_at.is_not(None),
                LineAccount.is_blocked.is_(False))).all()
            for user in users:
                # XZ_MULTI_RECIPIENT_SOURCE_KEY_20261103
                # The DB unique index is (source_type, source_id, channel), not
                # (source_type, source_id, recipient_id). Give EACH recipient a
                # distinct deterministic source ID to avoid collisions.
                source_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"xz-emergency:{incident['id']}:{stage}:{user.id}",
                )
                # Also recognize legacy IDs, so previously queued/sent alerts
                # do not get resent when the flag is eventually enabled.
                legacy_source_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"xz-emergency:{incident['id']}:{stage}",
                )
                exists = session.scalar(select(NotificationJob.id).where(
                    NotificationJob.source_type == 'jiaan_emergency',
                    NotificationJob.source_id.in_((source_id, legacy_source_id)),
                    NotificationJob.recipient_id == user.id))
                if exists:
                    continue
                notification = NotificationJob(
                    org_id=incident['org_id'], recipient_id=user.id,
                    source_type='jiaan_emergency', source_id=source_id,
                    channel='line', status='queued', payload={
                        'kind':'jiaan_emergency_alert',
                        'emergency_id':str(incident['id']), 'stage':stage,
                        # 分類代碼為固定的 7 種既有安全代碼（非自由文字），不含個案內容，可安全放進通知。
                        'category': incident['category'],
                        'incident_created_at': incident['created_at'].isoformat()})
                session.add(notification)
                session.flush()
                jobs.enqueue(session, 'notify', {'notification_id':str(notification.id)},
                             f'notify:{notification.id}', max_attempts=5)
                created += 1
    return created
