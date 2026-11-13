"""SOPB-only persistent Voice/SMS outbox; disabled by default.

Only loopback Mock Gateway is allowed. Requires isolated PG migration.
Sending is AT-LEAST-ONCE; stable provider idempotency key is mandatory.
A successful HTTP 2xx is accepted by mock, NOT handset delivery.
"""
from __future__ import annotations
import asyncio
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import text
from app.ack_escalation import execute_voice_sms_dispatch


def is_enabled() -> bool:
    # Two separate gates prevent enabling this via the existing LINE flag.
    return (os.getenv("XZ_SOPB_VOICE_OUTBOX", "off").lower() == "on"
            and os.getenv("XZ_SOPB_LOOPBACK_ONLY", "off").lower() == "on")


def stage(db) -> int:
    """INSERT ... SELECT in same transaction; UNIQUE(event_id) deduplicates.

    Lock the SOS row before staging to order with ACK transaction.
    """
    if not is_enabled():
        return 0
    result = db.execute(text("""
        WITH overdue AS (
          SELECT e.id, e.org_id FROM public.jiaan1030_emergencies e
          WHERE e.status = 'open'
            AND e.created_at <= now() - interval '60 seconds'
          ORDER BY e.created_at
          LIMIT 100
          FOR UPDATE OF e SKIP LOCKED
        )
        INSERT INTO public.sopb_voice_outbox
          (event_id, org_id, status, next_attempt_at)
        SELECT overdue.id, overdue.org_id, 'queued', now() FROM overdue
        ON CONFLICT (event_id) DO NOTHING
        RETURNING event_id
    """))
    return len(result.fetchall())


def _lease(db):
    """Caller commits lease BEFORE attempting any HTTP."""
    lease = uuid.uuid4()
    row = db.execute(text("""
        WITH candidate AS (
          SELECT o.event_id FROM public.sopb_voice_outbox o
          JOIN public.jiaan1030_emergencies e ON e.id=o.event_id AND e.org_id=o.org_id
          WHERE ((o.status IN ('queued','retry') AND o.next_attempt_at <= now())
                 OR (o.status='sending' AND o.leased_at < now() - interval '45 seconds'))
            AND o.attempts < 5 AND e.status='open'
          ORDER BY o.created_at
          LIMIT 1
          FOR UPDATE OF o SKIP LOCKED
        )
        UPDATE public.sopb_voice_outbox o
        SET status='sending', leased_at=now(), lease_token=:lease,
            attempts=attempts+1, updated_at=now()
        FROM candidate c WHERE o.event_id=c.event_id
        RETURNING o.event_id, o.org_id, o.attempts
    """), {"lease":lease}).mappings().first()
    return (dict(row),lease) if row else None


def _still_open(db, event_id, org_id) -> bool:
    # Recheck immediately before outbound request; ACK can still race after it.
    return bool(db.execute(text("""
        SELECT 1 FROM public.jiaan1030_emergencies
        WHERE id=:event AND org_id=:org AND status='open'
    """), {"event":event_id,"org":org_id}).scalar_one_or_none())


def _finish(db, event_id, lease, status, error_code=None, http_status=None):
    db.execute(text("""
        UPDATE public.sopb_voice_outbox
        SET status=:status, last_error_code=:error,
            last_http_status=:http, accepted_at=CASE WHEN :status='accepted' THEN now() ELSE accepted_at END,
            next_attempt_at=CASE WHEN :status='retry' THEN now()+interval '60 seconds' ELSE next_attempt_at END,
            lease_token=NULL, updated_at=now()
        WHERE event_id=:event AND lease_token=:lease AND status='sending'
    """), {"status":status, "error":error_code, "http":http_status,
           "event":event_id, "lease":lease})


def dispatch_one(session_factory) -> bool:
    if not is_enabled():
        return False
    db=session_factory()
    try:
        leased=_lease(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    if leased is None:
        return False
    row, lease = leased
    db=session_factory()
    try:
        pending=_still_open(db,row['event_id'],row['org_id'])
        db.rollback()
    finally:
        db.close()
    if not pending:
        db=session_factory()
        try:
            _finish(db,row['event_id'],lease,'cancelled','no_longer_open')
            db.commit()
        finally:
            db.close()
        return True
    try:
        reply=asyncio.run(execute_voice_sms_dispatch(str(row['event_id']),str(row['org_id'])))
        status='accepted' if reply.get('accepted') else 'retry'
        reason=None if status=='accepted' else 'gateway_not_accepted'
        http_code=reply.get('http_status')
    except Exception as exc:
        # Never record tokens, payloads or HTTP response bodies in DB.
        reason=type(exc).__name__[:48]
        status='failed' if row['attempts']>=5 else 'retry'
        http_code=None
    db=session_factory()
    try:
        _finish(db,row['event_id'],lease,status,reason,http_code)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return True
