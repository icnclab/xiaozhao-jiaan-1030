"""Opt-in Web Push for Jiaan. Off by default. No patient or address data in payload.

Requires pywebpush and configured VAPID keys. Cross-app background delivery depends
on browser, platform and notification permissions; never represents guaranteed alarms.
"""
from __future__ import annotations
import logging
import hashlib
import hmac
import os
from pathlib import Path
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)
MANAGERS = ('supervisor', 'director', 'admin')
STAGES = (('new', 0), ('unacknowledged_60s', 60), ('unacknowledged_180s', 180))


def enabled() -> bool:
    from app.config import get_settings
    if get_settings().is_uat:
        return False
    return os.getenv('JIAAN_WEBPUSH_DISPATCH', 'off').strip().lower() == 'on'


def public_key() -> str:
    from app.config import get_settings
    if get_settings().is_uat:
        return ""
    return os.getenv('JIAAN_VAPID_PUBLIC_KEY', '').strip()


def endpoint_allowed(endpoint: str) -> bool:
    """Limit notification endpoints to standard browser push providers; avoid SSRF."""
    try:
        url = urlparse(endpoint)
        host = (url.hostname or '').lower()
        if url.scheme != 'https' or url.username or url.password or url.port not in (None, 443):
            return False
        if len(endpoint) > 2048 or not host:
            return False
        return (host in {'fcm.googleapis.com', 'updates.push.services.mozilla.com',
                         'web.push.apple.com', 'wns2-par02p.notify.windows.com'}
                or host.endswith('.push.apple.com')
                or host.endswith('.notify.windows.com')
                or host == 'updates.push.services.mozilla.com')
    except (ValueError, AttributeError):
        return False


def _subscription_fernet():
    """Fail closed unless a separate subscription encryption key is provided."""
    from cryptography.fernet import Fernet
    key = os.environ.get('JIAAN_WEBPUSH_SUBSCRIPTION_KEY', '').strip()
    if not key:
        raise RuntimeError('WEBPUSH_SUBSCRIPTION_KEY_NOT_CONFIGURED')
    try:
        return Fernet(key.encode('ascii'))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError('WEBPUSH_SUBSCRIPTION_KEY_INVALID') from exc


def endpoint_hash(endpoint: str) -> str:
    """Stable, keyed lookup without exposing the actual push endpoint."""
    key = os.environ.get('JIAAN_WEBPUSH_SUBSCRIPTION_KEY', '').strip()
    _subscription_fernet()  # validate length and syntax
    return hmac.new(key.encode('ascii'), endpoint.encode('utf-8'), hashlib.sha256).hexdigest()


def encrypt_subscription_value(value: str) -> str:
    return 'enc:v1:' + _subscription_fernet().encrypt(value.encode('utf-8')).decode('ascii')


def decrypt_subscription_value(value: str) -> str:
    """Never silently accept plaintext values in the protected pipeline."""
    if not isinstance(value, str) or not value.startswith('enc:v1:'):
        raise RuntimeError('WEBPUSH_LEGACY_PLAINTEXT_SUBSCRIPTION_REFUSED')
    try:
        return _subscription_fernet().decrypt(value[len('enc:v1:'):].encode('ascii')).decode('utf-8')
    except Exception as exc:
        raise RuntimeError('WEBPUSH_SUBSCRIPTION_DECRYPT_FAILED') from exc


def alert_payload(eid: uuid.UUID, stage: str) -> dict:
    titles = {'new':'嘉安緊急通報待接手', 'unacknowledged_60s':'嘉安緊急通報尚未接手（60秒）',
              'unacknowledged_180s':'嘉安緊急通報逾時（180秒）'}
    return {'title': titles[stage], 'body': '有一筆緊急通報，請立即開啟小照確認；危急情況依機構流程聯絡119／110。',
            'emergency_id':str(eid), 'stage':stage, 'url':'/api/jiaan1030/emergency-ui'}


def sweep(db: Session, now: datetime | None = None) -> int:
    """Atomically stage notifications for active manager devices of same org.

    Idempotent via UNIQUE(emergency_id,stage,subscription_id). The caller commits.
    """
    if not enabled():
        return 0
    now = now or datetime.now(timezone.utc)
    if not db.execute(text('SELECT pg_try_advisory_xact_lock(16430103, 20261103)')).scalar_one():
        return 0
    incidents = db.execute(text('''
        SELECT id, org_id, created_at FROM jiaan1030_emergencies
        WHERE status='open' AND created_at<=:now ORDER BY created_at LIMIT 100
    '''), {'now':now}).mappings().all()
    count=0
    for incident in incidents:
        age = max(0, (now - incident['created_at']).total_seconds())
        for stage, seconds in STAGES:
            if age < seconds:
                continue
            count += db.execute(text('''
                INSERT INTO jiaan_webpush_deliveries (id, emergency_id, subscription_id, stage, status)
                SELECT gen_random_uuid(), :eid, s.id, :stage, 'queued'
                FROM jiaan_webpush_subscriptions s
                JOIN users u ON u.id=s.user_id
                WHERE s.org_id=:org AND u.org_id=:org
                  AND s.is_active=true AND u.is_active=true
                  AND u.role IN ('supervisor','director','admin')
                  AND (:stage = 'unacknowledged_180s' OR u.role = 'supervisor')
                ON CONFLICT (emergency_id,subscription_id,stage) DO NOTHING
            '''), {'eid':incident['id'], 'org':incident['org_id'], 'stage':stage}).rowcount or 0
    return count


def _send_one(db: Session, delivery: dict) -> None:
    """Must be used in worker only; guard latest status and manager authorization."""
    # Acquire per-delivery claim via FOR UPDATE SKIP LOCKED in dispatch_due().
    row = db.execute(text('''
        SELECT a.status AS incident_status, a.org_id AS incident_org,
               s.endpoint,s.p256dh,s.auth,s.is_active AS sub_active,
               s.org_id AS subscription_org,
               u.is_active AS user_active, u.role AS user_role,u.org_id AS user_org
        FROM jiaan1030_emergencies a
        JOIN jiaan_webpush_subscriptions s ON s.id=:sid
        JOIN users u ON u.id=s.user_id
        WHERE a.id=:eid
    '''), {'sid':delivery['subscription_id'],'eid':delivery['emergency_id']}).mappings().first()
    if (not row or row['incident_status'] != 'open' or not row['sub_active']
            or not row['user_active'] or row['user_role'] not in MANAGERS
            or row['incident_org'] != row['user_org']
            or row['incident_org'] != row['subscription_org']
            ):
        db.execute(text('UPDATE jiaan_webpush_deliveries SET status=\'skipped\' WHERE id=:id'), {'id':delivery['id']})
        return
    # Decrypt only in memory immediately before sending; never log subscriptions.
    endpoint = decrypt_subscription_value(row['endpoint'])
    p256dh = decrypt_subscription_value(row['p256dh'])
    auth = decrypt_subscription_value(row['auth'])
    if not endpoint_allowed(endpoint):
        db.execute(text("UPDATE jiaan_webpush_deliveries SET status='skipped' WHERE id=:id"), {'id':delivery['id']})
        return
    import json
    from pywebpush import webpush, WebPushException
    from cryptography.hazmat.primitives import serialization
    # pywebpush accepts a PEM file path, not raw PEM text.  This is the
    # protected file already used by the successful one-device test.
    pem_path = (Path(__file__).resolve().parents[3]
                / 'deploy' / 'fieldtest' / '.local_webpush_secrets' / 'vapid_private.pem')
    if not pem_path.is_file():
        raise RuntimeError('WEBPUSH_VAPID_PEM_FILE_MISSING')
    # Fail closed on a key mismatch: never silently dispatch using a different key.
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    try:
        file_key = load_pem_private_key(pem_path.read_bytes(), password=None)
        runtime_key = load_pem_private_key(os.environ['JIAAN_VAPID_PRIVATE_KEY'].encode('utf-8'), password=None)
        if file_key.private_numbers() != runtime_key.private_numbers():
            raise RuntimeError('WEBPUSH_VAPID_RUNTIME_KEY_MISMATCH')
    except (ValueError, TypeError, OSError, UnicodeError) as exc:
        raise RuntimeError('WEBPUSH_VAPID_KEY_INVALID') from exc
    subject = os.environ['JIAAN_VAPID_SUBJECT']
    data = json.dumps(alert_payload(delivery['emergency_id'],delivery['stage']), ensure_ascii=False)
    try:
        webpush(subscription_info={'endpoint':endpoint, 'keys':{'p256dh':p256dh,'auth':auth}},
                data=data, vapid_private_key=str(pem_path), vapid_claims={'sub':subject},
                headers={'Urgency':'high'}, ttl=300, timeout=8)
        status='accepted'
    except WebPushException as exc:
        code=getattr(getattr(exc,'response',None),'status_code',None)
        if code in (404,410):
            db.execute(text('UPDATE jiaan_webpush_subscriptions SET is_active=false WHERE id=:id'),
                       {'id':delivery['subscription_id']})
        log.warning('webpush failed %s', code or type(exc).__name__)
        status='failed'
    db.execute(text('''UPDATE jiaan_webpush_deliveries SET status=:status, attempted_at=now(), attempts=attempts+1
        WHERE id=:id'''),{'status':status,'id':delivery['id']})


def dispatch_due(db: Session, limit: int=10) -> int:
    if not enabled():
        return 0
    if not all(os.environ.get(k) for k in ('JIAAN_VAPID_PRIVATE_KEY','JIAAN_VAPID_PUBLIC_KEY','JIAAN_VAPID_SUBJECT')):
        return 0
    rows=db.execute(text('''
        SELECT id,emergency_id,subscription_id,stage FROM jiaan_webpush_deliveries
        WHERE (status='queued' OR (status='failed' AND attempts < 3
               AND attempted_at <= now() - interval '60 seconds'))
        ORDER BY created_at, id LIMIT :limit FOR UPDATE SKIP LOCKED
    '''), {'limit':limit}).mappings().all()
    for row in rows:
        _send_one(db,dict(row))
    return len(rows)
