"""Fail-closed overdue SOS claim and explicitly opt-in LOOPBACK-only HTTP dispatch.

Not connected to production worker. Only for an authorized isolated PostgreSQL
sandbox. This module does not create durable outbox jobs; never enable live SOS.
"""
from __future__ import annotations
import ipaddress
import os
from urllib.parse import urlsplit
from uuid import UUID
import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session


def claim_overdue_emergency(db: Session, event_id: str):
    """Lock a genuinely open and >=60s overdue event in caller's DB transaction.

    Caller must commit/rollback promptly; do not perform HTTP under the row lock.
    This is a claim check ONLY, not durable deduplication or queue insertion.
    """
    eid = UUID(str(event_id))
    row = db.execute(text("""
        SELECT id, org_id, status, created_at
        FROM public.jiaan1030_emergencies
        WHERE id = :event_id
          AND status = 'open'
          AND created_at <= now() - INTERVAL '60 seconds'
        FOR UPDATE SKIP LOCKED
    """), {"event_id": eid}).mappings().first()
    return dict(row) if row is not None else None


def _loopback_target() -> str:
    if os.environ.get("XZ_SOPB_LOOPBACK_ONLY", "off").lower() != "on":
        raise RuntimeError("sopb_loopback_disabled")
    url = os.environ.get("XZ_SOPB_MOCK_GATEWAY_URL", "")
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1") or parsed.username or parsed.password:
        raise RuntimeError("loopback_gateway_url_required")
    try:
        if not ipaddress.ip_address(parsed.hostname).is_loopback:
            raise RuntimeError("loopback_gateway_url_required")
    except ValueError as exc:
        raise RuntimeError("loopback_gateway_url_required") from exc
    if not parsed.port:
        raise RuntimeError("loopback_port_required")
    return url


async def execute_voice_sms_dispatch(event_id: str, org_id: str) -> dict:
    """HTTP request to local Mock Gateway only; never claim delivered/called.

    For E2E trial, *caller* must use a committed, unique outbox entry and retry
    only according to its persisted state. No PHI is sent.
    """
    event = UUID(str(event_id))
    org = UUID(str(org_id))
    url = _loopback_target()
    payload = {
        "event_ref": str(event), "to_org": str(org),
        "message": "小照緊急事件仍未接手，請依機構人工通報 SOP 處理。",
    }
    headers = {"Idempotency-Key": f"sopb-voice-{event}"}
    async with httpx.AsyncClient(timeout=5.0, trust_env=False, follow_redirects=False) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        if response.status_code not in (200, 201, 202):
            raise RuntimeError("gateway_unexpected_status")
        return {"accepted": True, "http_status": response.status_code,
                "event_ref": str(event), "delivery_verified": False}
