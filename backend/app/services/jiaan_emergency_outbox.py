"""Transactional outbox for the 'new'-stage SOS web-push alert.

Reuses, rather than duplicates:
- public.jobs for idempotency, retry/backoff, and lease/fencing (via jobs.enqueue /
  jobs.claim; this module never introduces a second job queue or worker loop).
- public.jiaan_webpush_deliveries for per-recipient delivery state, extended by the
  2026-11-14 migration with job_id / expires_at / provider_accepted_at / app_opened_at /
  last_error_class (see run/integration_outbox_final_review_20261114_170707/
  REVIEWED_OUTBOX_SCHEMA.sql).

Off by default: gated by the same JIAAN_WEBPUSH_DISPATCH flag as the existing
sweep()/dispatch_due() poll path in jiaan_webpush.py, which stays off in every
deployed environment. No HANDLERS entry exists in app/worker.py for the job kind
this module enqueues, so even if a real worker process ever claimed one of these
jobs it would fail closed ("unknown job kind") rather than attempt delivery; no
dispatcher is wired up by this batch.

Caller contract: the caller must run create_new_stage_outbox() in the SAME
session as the emergency insert it belongs to, and must commit exactly once
after. This module never calls session.commit() or session.rollback().
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import jobs
from app.services.jiaan_webpush import alert_payload, decrypt_subscription_value, enabled, endpoint_allowed

JOB_KIND = "jiaan_emergency_webpush_outbox"
DELIVERY_TTL_SECONDS = 300  # matches the migration's backfill default (5 minutes)


class DispatchDisabled(Exception):
    """JIAAN_WEBPUSH_DISPATCH is off; caller must park, not fail, the job."""


@dataclass(frozen=True)
class PushResult:
    accepted: bool
    error_class: str | None = None


@dataclass(frozen=True)
class PushMessage:
    """Everything a Provider needs to attempt one send -- and nothing more.

    dispatch_one() builds this only after its own TTL/org/role/status checks
    already passed, so a Provider implementation has no business-rule
    decision left to make or bypass; it can only attempt delivery or not.
    """
    delivery_id: uuid.UUID
    subscription_id: uuid.UUID
    emergency_id: uuid.UUID
    stage: str
    endpoint: str
    p256dh: str
    auth: str
    payload: dict


class PushProvider(Protocol):
    def send(self, message: PushMessage) -> PushResult: ...


class MockPushProvider:
    """Test-only stand-in. Never constructed or wired by any production code
    path in this module -- only isolated tests inject it via dispatch_one()'s
    `provider` parameter. Records every call for assertions; never performs
    network I/O.
    """

    def __init__(self, *, accept: bool = True, error_class: str | None = None):
        self.accept = accept
        self.error_class = error_class
        self.calls: list[dict] = []

    def send(self, message: PushMessage) -> PushResult:
        self.calls.append({
            'delivery_id': message.delivery_id, 'subscription_id': message.subscription_id,
            'emergency_id': message.emergency_id, 'stage': message.stage,
            'endpoint': message.endpoint,
        })
        return PushResult(accepted=self.accept, error_class=self.error_class)


def create_new_stage_outbox(db: Session, *, emergency_id: uuid.UUID, org_id: uuid.UUID,
                             now: datetime | None = None) -> int:
    """Insert 'new'-stage deliveries and their matching jobs for one emergency.

    Follows the 4-step order documented in REVIEWED_OUTBOX_SCHEMA.sql (lines 68-76):
    insert delivery -> enqueue job -> set delivery.job_id -> caller commits once.
    Delivery-insert-first means a duplicate call (same emergency+subscription+stage)
    is rejected by the existing UNIQUE(emergency_id, subscription_id, stage) index
    before any job is ever enqueued, so no orphaned job can result from a retry.

    Returns the number of deliveries newly created (0 when disabled or when
    everything for this emergency already exists).
    """
    if not enabled():
        return 0
    now = now or datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=DELIVERY_TTL_SECONDS)
    subscriptions = db.execute(text('''
        SELECT s.id AS subscription_id FROM jiaan_webpush_subscriptions s
        JOIN users u ON u.id = s.user_id
        WHERE s.org_id = :org AND u.org_id = :org
          AND s.is_active = true AND u.is_active = true AND u.role = 'supervisor'
    '''), {'org': org_id}).mappings().all()
    created = 0
    for sub in subscriptions:
        delivery_id = uuid.uuid4()
        result = db.execute(text('''
            INSERT INTO jiaan_webpush_deliveries
              (id, emergency_id, subscription_id, stage, status, expires_at)
            VALUES (:id, :eid, :sid, 'new', 'queued', :expires_at)
            ON CONFLICT (emergency_id, subscription_id, stage) DO NOTHING
        '''), {'id': delivery_id, 'eid': emergency_id, 'sid': sub['subscription_id'],
               'expires_at': expires_at})
        if result.rowcount == 0:
            continue
        job_id = uuid.uuid4()
        jobs.enqueue(
            db, JOB_KIND,
            {'delivery_id': str(delivery_id), 'emergency_id': str(emergency_id)},
            f'emergency-webpush:{delivery_id}',
            max_attempts=5, job_id=job_id,
        )
        db.execute(text('UPDATE jiaan_webpush_deliveries SET job_id = :jid WHERE id = :did'),
                   {'jid': job_id, 'did': delivery_id})
        created += 1
    return created


def dispatch_one(db: Session, delivery_id: uuid.UUID, *, provider: PushProvider | None = None,
                  now: datetime | None = None) -> None:
    """Worker handler body for JOB_KIND. Caller (app/worker.py) commits/rolls back.

    Safety order, checked before anything is ever considered "accepted":
    1. Feature flag off -> raise DispatchDisabled immediately; no row read, no provider call.
    2. Already 'accepted' -> idempotent no-op (a prior attempt succeeded and only the
       job-completion commit was lost to a crash; never call the provider twice).
    3. Anything else not (queued/failed), expired, wrong org, inactive, wrong role,
       or emergency no longer open (cancelled/resolved/missing) -> mark 'skipped', return.
    4. Otherwise call the injected provider and record provider_accepted_at only --
       never acknowledged_at, never app_opened_at.

    provider=None in any code path that reaches step 4 is a configuration error
    (no real provider is wired by this batch): raises rather than silently
    pretending to have sent anything.
    """
    if not enabled():
        raise DispatchDisabled('webpush dispatch disabled by feature flag')
    now = now or datetime.now(timezone.utc)
    row = db.execute(text('''
        SELECT d.id, d.status, d.expires_at, d.stage, d.emergency_id, d.subscription_id,
               e.status AS emergency_status, e.org_id AS emergency_org,
               s.org_id AS subscription_org, s.is_active AS subscription_active,
               s.endpoint, s.p256dh, s.auth,
               u.is_active AS user_active, u.role AS user_role, u.org_id AS user_org
        FROM jiaan_webpush_deliveries d
        JOIN jiaan1030_emergencies e ON e.id = d.emergency_id
        JOIN jiaan_webpush_subscriptions s ON s.id = d.subscription_id
        JOIN users u ON u.id = s.user_id
        WHERE d.id = :did
        FOR UPDATE OF d
    '''), {'did': delivery_id}).mappings().first()
    if row is None:
        return
    if row['status'] == 'accepted':
        return
    valid = (
        row['status'] in ('queued', 'failed')
        and row['expires_at'] > now
        and row['stage'] == 'new'
        and row['emergency_status'] == 'open'
        and row['emergency_org'] == row['subscription_org'] == row['user_org']
        and row['subscription_active'] and row['user_active']
        and row['user_role'] == 'supervisor'
    )
    if not valid:
        db.execute(text("UPDATE jiaan_webpush_deliveries SET status = 'skipped' WHERE id = :id"),
                   {'id': delivery_id})
        return
    # Decrypt only in memory, immediately before the (possible) send; same
    # discipline as jiaan_webpush.py's _send_one(). endpoint_allowed() blocks
    # SSRF-style endpoints even for an already-authorized, unexpired delivery.
    endpoint = decrypt_subscription_value(row['endpoint'])
    if not endpoint_allowed(endpoint):
        db.execute(text("UPDATE jiaan_webpush_deliveries SET status = 'skipped' WHERE id = :id"),
                   {'id': delivery_id})
        return
    if provider is None:
        raise RuntimeError('WEBPUSH_PROVIDER_NOT_CONFIGURED: no production dispatcher is wired yet')
    message = PushMessage(
        delivery_id=delivery_id, subscription_id=row['subscription_id'],
        emergency_id=row['emergency_id'], stage=row['stage'], endpoint=endpoint,
        p256dh=decrypt_subscription_value(row['p256dh']), auth=decrypt_subscription_value(row['auth']),
        payload=alert_payload(row['emergency_id'], row['stage']),
    )
    result = provider.send(message)
    if result.accepted:
        db.execute(text('''
            UPDATE jiaan_webpush_deliveries
            SET status = 'accepted', provider_accepted_at = now(), attempted_at = now(),
                attempts = attempts + 1
            WHERE id = :id
        '''), {'id': delivery_id})
        return
    db.execute(text('''
        UPDATE jiaan_webpush_deliveries
        SET status = 'failed', attempted_at = now(), attempts = attempts + 1,
            last_error_class = :cls
        WHERE id = :id
    '''), {'id': delivery_id, 'cls': (result.error_class or 'unknown')[:200]})
    db.commit()
    raise RuntimeError(f'webpush_provider_rejected:{result.error_class or "unknown"}')


def due_deliveries_for_dispatch(db: Session, *, now: datetime | None = None, limit: int = 50) -> list[dict]:
    """Read-only: deliveries a future dispatcher could claim right now.

    Mirrors ix_jiaan_webpush_delivery_due: only queued/failed rows whose TTL has
    not expired. Expired rows are excluded so a late-starting worker cannot
    resurrect a stale alert as if it were new.
    """
    now = now or datetime.now(timezone.utc)
    rows = db.execute(text('''
        SELECT d.id, d.emergency_id, d.subscription_id, d.job_id, d.expires_at
        FROM jiaan_webpush_deliveries d
        WHERE d.status IN ('queued', 'failed') AND d.expires_at > :now
        ORDER BY d.created_at LIMIT :limit
    '''), {'now': now, 'limit': limit}).mappings().all()
    return [dict(r) for r in rows]
