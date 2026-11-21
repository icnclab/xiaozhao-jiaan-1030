"""Jiaan 2026-10-30 interview: urgent report and supervisor handoff.

Web-only active-page monitoring; NEVER claims background/push delivery.
No patient names, addresses or medical details are stored in this module.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import User
from app.services import audit
from app.services import jiaan_emergency_outbox

router = APIRouter()
PREFIX = '/jiaan1030'
ROOT = Path(__file__).resolve().parent
CATEGORIES = ('fall', 'violence', 'injury', 'unresponsive', 'traffic', 'self_harm', 'other')
MANAGERS = ('supervisor', 'director', 'admin')
RESPONDERS = ('caregiver', 'supervisor', 'director', 'admin')

class NewEmergency(BaseModel):
    category: Literal['fall', 'violence', 'injury', 'unresponsive', 'traffic', 'self_harm', 'other']
    client_request_id: uuid.UUID

class Handoff(BaseModel):
    client_request_id: uuid.UUID
    # 2026-11-14 新增：結束通報時鼓勵填寫原因（非必填，不破壞既有呼叫端）；
    # 不得含個案細節，僅供事件處理摘要與稽核使用。
    reason: str | None = Field(default=None, max_length=200)

class CancelReport(BaseModel):
    client_request_id: uuid.UUID
    # 取消誤報「一定」要填原因（跟結束通報不同，取消代表這筆通報本身不成立）。
    reason: str = Field(min_length=1, max_length=200)

    @field_validator('reason')
    @classmethod
    def validate_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('取消原因（必填）不可空白')
        return value


def error(code: int, name: str, message: str):
    raise HTTPException(status_code=code, detail={'code': name, 'message': message})


def check_role(user: User, roles: tuple[str, ...]) -> None:
    # Organization scope is enforced by every emergency SELECT/INSERT/UPDATE.
    # Staff identity is their authenticated role and org_id, never a username prefix:
    # legitimate 嘉安 staff may use test_sv002 or other non-jiaan_ usernames.
    if (not getattr(user, 'is_active', False) or user.role not in roles
            or getattr(user, 'org_id', None) is None):
        error(403, 'forbidden', '無權限執行此操作')


def serialize(row: dict) -> dict:
    return {
        'id': str(row['id']), 'category': row['category'], 'status': row['status'],
        'created_at': row['created_at'].isoformat(),
        'acknowledged_at': row['acknowledged_at'].isoformat() if row['acknowledged_at'] else None,
        'resolved_at': row['resolved_at'].isoformat() if row['resolved_at'] else None,
        'created_by': str(row['created_by']),
        'acknowledged_by': str(row['acknowledged_by']) if row['acknowledged_by'] else None,
        'resolved_by': str(row['resolved_by']) if row['resolved_by'] else None,
        # 僅供居督／主任辨識「誰接手」，不暴露個案內容；同機構才看得到（既有 org 範圍不變）。
        'acknowledged_by_name': row.get('acknowledged_by_name'),
        'resolved_by_name': row.get('resolved_by_name'),
        'delivery': 'web_poll_only',
    }


_WITH_NAMES_SELECT = '''
    SELECT e.id, e.org_id, e.created_by, e.client_request_id, e.category, e.status,
           e.created_at, e.acknowledged_at, e.acknowledged_by, e.resolved_at, e.resolved_by,
           au.display_name AS acknowledged_by_name, ru.display_name AS resolved_by_name
    FROM jiaan1030_emergencies e
    LEFT JOIN users au ON au.id = e.acknowledged_by
    LEFT JOIN users ru ON ru.id = e.resolved_by
'''


def get_one(db: Session, user: User, emergency_id: uuid.UUID, lock: bool = False):
    suffix = ' FOR UPDATE OF e' if lock else ''
    row = db.execute(text(
        _WITH_NAMES_SELECT + ' WHERE e.id = :eid AND e.org_id = :org' + suffix
    ), {'eid': emergency_id, 'org': user.org_id}).mappings().first()
    if not row:
        error(404, 'not_found', '找不到這筆通報')
    if user.role == 'caregiver' and row['created_by'] != user.id:
        error(404, 'not_found', '找不到這筆通報')
    return dict(row)


def record_event(db: Session, eid: uuid.UUID, user: User, kind: str, old: str | None, new: str | None) -> None:
    db.execute(text('''
        INSERT INTO jiaan1030_emergency_events
          (id, emergency_id, actor_id, event_type, from_status, to_status)
        VALUES (:id, :eid, :uid, :kind, :old, :new)
    '''), {'id': uuid.uuid4(), 'eid': eid, 'uid': user.id,
           'kind': kind, 'old': old, 'new': new})


@router.get(PREFIX + '/emergency-ui', include_in_schema=False)
def emergency_page():
    # 舊書籤與尚未更新的入口一律安全導向第五版 SOS；443 與 8443 的
    # sessionStorage 不共用，因此新版 SOS 會要求使用者重新登入，不假裝單一登入。
    return RedirectResponse('https://stust.tail379935.ts.net:8443/api/jiaan1030/sos-app/',
                            status_code=307, headers={'Cache-Control': 'no-store'})


@router.get(PREFIX + '/launcher.js', include_in_schema=False)
def emergency_launcher():
    return Response((ROOT / 'jiaan1030_emergency_launcher.js').read_text(encoding='utf-8'),
                    media_type='application/javascript',
                    headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.post(PREFIX + '/emergencies', status_code=201)
def create_emergency(body: NewEmergency, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    check_role(user, RESPONDERS)
    # Database unique key makes double taps/retries idempotent.
    existing = db.execute(text('''
        SELECT id FROM jiaan1030_emergencies
        WHERE created_by=:uid AND client_request_id=:req
    '''), {'uid': user.id, 'req': str(body.client_request_id)}).scalar_one_or_none()
    if existing:
        row = get_one(db, user, existing)
        if row['category'] != body.category:
            error(409, 'request_reused', '同一請求編號已用於不同通報')
        return serialize(row)
    eid = uuid.uuid4()
    # A second concurrent identical request can hit unique constraint: caller retries GET via UI.
    db.execute(text('''
        INSERT INTO jiaan1030_emergencies
          (id, org_id, created_by, client_request_id, category, status)
        VALUES (:id, :org, :uid, :req, :category, 'open')
        ON CONFLICT (created_by, client_request_id) DO NOTHING
    '''), {'id': eid, 'org': user.org_id, 'uid': user.id,
           'req': str(body.client_request_id), 'category': body.category})
    row_id = db.execute(text('''
        SELECT id, category FROM jiaan1030_emergencies
        WHERE created_by=:uid AND client_request_id=:req
    '''), {'uid': user.id, 'req': str(body.client_request_id)}).mappings().one()
    if row_id['category'] != body.category:
        db.rollback()
        error(409, 'request_reused', '同一請求編號已用於不同通報')
    if row_id['id'] == eid:
        record_event(db, eid, user, 'created', None, 'open')
        # Same session/transaction as the emergency insert above; a single
        # db.commit() below makes event + delivery + job visible together,
        # and any failure anywhere in this function rolls all of it back.
        jiaan_emergency_outbox.create_new_stage_outbox(db, emergency_id=eid, org_id=user.org_id)
    db.commit()
    return serialize(get_one(db, user, row_id['id']))


@router.get(PREFIX + '/emergencies')
def list_emergencies(status: Literal['active', 'resolved', 'all'] = 'active',
                     user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    check_role(user, RESPONDERS)
    # 'resolved' 這個查詢參數代表「已結案的歷史清單」，同時包含真正處理完成(resolved)
    # 跟取消的誤報(cancelled)，兩者在前端會用不同文字呈現，不會混為一談。
    where = "e.status IN ('open','acknowledged')" if status == 'active' else ("e.status IN ('resolved','cancelled')" if status == 'resolved' else 'TRUE')
    own = ' AND e.created_by = :uid' if user.role == 'caregiver' else ''
    # Restrict to the requester's organisation, then restrict caregivers to their own reports.
    params = {'org': user.org_id, 'uid': user.id}
    rows = db.execute(text(
        _WITH_NAMES_SELECT + ' WHERE e.org_id=:org AND ' + where + own + ' ORDER BY e.created_at DESC LIMIT 100'
    ), params).mappings().all()
    return {'items': [serialize(dict(row)) for row in rows],
            'delivery': 'web_poll_only',
            'warning': '網頁提醒不保證其他 APP、鎖定畫面或斷網時送達；危急先撥 119／110 並直接聯絡督導。'}


@router.get(PREFIX + '/emergencies/{emergency_id}/history')
def emergency_history(emergency_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    check_role(user, RESPONDERS)
    get_one(db, user, emergency_id)
    # actor_role 是「現在」的角色（即時 join users.role），不是事件發生當時的角色快照；
    # events 表沒有存角色快照欄位。這在絕大多數情況下沒差（角色很少變動），但如果某人
    # 事後被降／升職，歷史紀錄顯示的角色稱呼會變成「現在」的角色，不是當時的。前端顯示
    # 文字會加註這一點不是假造，只是即時 join 的已知限制。
    rows = db.execute(text('''
        SELECT e.event_type, e.actor_id, e.from_status, e.to_status, e.created_at,
               u.display_name AS actor_name, u.role AS actor_role
        FROM jiaan1030_emergency_events e
        JOIN jiaan1030_emergencies a ON a.id=e.emergency_id
        LEFT JOIN users u ON u.id = e.actor_id
        WHERE e.emergency_id=:eid AND a.org_id=:org
        ORDER BY e.created_at, CASE e.event_type WHEN 'created' THEN 0 WHEN 'acknowledged' THEN 1
                 WHEN 'resolved' THEN 2 WHEN 'cancelled' THEN 2 ELSE 3 END, e.id
    '''), {'eid': emergency_id, 'org': user.org_id}).mappings().all()
    return {'items': [dict(event_type=r['event_type'], actor_id=str(r['actor_id']), actor_name=r['actor_name'],
                           actor_role=r['actor_role'],
                           from_status=r['from_status'], to_status=r['to_status'],
                           created_at=r['created_at'].isoformat()) for r in rows]}


@router.post(PREFIX + '/emergencies/{emergency_id}/acknowledge')
def acknowledge(emergency_id: uuid.UUID, body: Handoff,
                user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    check_role(user, MANAGERS)
    row = get_one(db, user, emergency_id, lock=True)
    if row['status'] == 'open':
        db.execute(text('''
            UPDATE jiaan1030_emergencies
            SET status='acknowledged', acknowledged_by=:uid, acknowledged_at=now()
            WHERE id=:eid AND org_id=:org AND status='open'
        '''), {'uid': user.id, 'eid': emergency_id, 'org': user.org_id})
        record_event(db, emergency_id, user, 'acknowledged', 'open', 'acknowledged')
        audit.record(db, 'sos.acknowledge', actor=user, target_type='emergency', target_id=emergency_id)
        db.commit()
    elif row['status'] == 'acknowledged' and row['acknowledged_by'] == user.id:
        db.rollback()
    else:
        db.rollback()
        error(409, 'already_claimed_or_resolved', '已有其他督導接手或案件已解除')
    return serialize(get_one(db, user, emergency_id))


@router.post(PREFIX + '/emergencies/{emergency_id}/resolve')
def resolve(emergency_id: uuid.UUID, body: Handoff,
            user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    check_role(user, MANAGERS)
    row = get_one(db, user, emergency_id, lock=True)
    if row['status'] == 'resolved':
        db.rollback()
        return serialize(row)
    if row['status'] != 'acknowledged':
        db.rollback()
        error(409, 'not_acknowledged', '須先由督導接手才能解除')
    if row['acknowledged_by'] != user.id and user.role not in ('director','admin'):
        db.rollback()
        error(403, 'handoff_owner_only', '只有接手督導或主任／管理員可解除')
    db.execute(text('''
        UPDATE jiaan1030_emergencies
        SET status='resolved', resolved_by=:uid, resolved_at=now()
        WHERE id=:eid AND org_id=:org AND status='acknowledged'
    '''), {'uid': user.id, 'eid': emergency_id, 'org': user.org_id})
    record_event(db, emergency_id, user, 'resolved', 'acknowledged', 'resolved')
    audit.record(db, 'sos.resolve', actor=user, target_type='emergency', target_id=emergency_id,
                 meta={'reason': body.reason} if body.reason else {})
    db.commit()
    return serialize(get_one(db, user, emergency_id))


# XZ_SOS_CANCEL_FALSE_ALARM_V1 - 2026-11-14：區分「取消尚未接手的誤報」跟「結束已處理的
# 通報」是兩種不同業務意義的操作，不能共用 resolve()。只允許從 open 轉成 cancelled；
# 一旦有人 acknowledge，就不再是「誤報可以單方面撤銷」的情境，必須走 resolve()，避免
# 用「取消」掩蓋掉一筆已經有人在處理的真實事件。原通報人（確認是自己誤觸/誤判）或本
# 機構督導／主任／管理員都可以取消；照服員不能取消別人的通報（避免冒用督導權限）。
# 「取消已完成的ACK接手」(把 acknowledged 退回 open) 沒有安全的既定規則，本次不實作，
# 也不在這裡新增任何讓事件倒退回之前狀態的路徑。
@router.post(PREFIX + '/emergencies/{emergency_id}/cancel')
def cancel(emergency_id: uuid.UUID, body: CancelReport,
           user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    check_role(user, RESPONDERS)
    row = get_one(db, user, emergency_id, lock=True)
    if row['status'] not in ('open', 'cancelled'):
        db.rollback()
        error(409, 'not_cancellable', '只有尚未接手的通報才能取消為誤報；已接手的通報請用「結束通報」')
    is_reporter = row['created_by'] == user.id
    is_manager = user.role in MANAGERS
    if not (is_reporter or is_manager):
        db.rollback()
        error(403, 'forbidden', '只有原通報人或本機構督導／主任／管理員可取消尚未接手的通報')
    # A retry by the actor who already cancelled is a successful no-op.
    # Other actors cannot turn an already cancelled event into their action.
    if row['status'] == 'cancelled':
        if row['resolved_by'] == user.id:
            db.rollback()
            return serialize(row)
        db.rollback()
        error(409, 'not_cancellable', '通報已取消，不能重複由其他人取消')
    updated = db.execute(text('''
        UPDATE jiaan1030_emergencies
        SET status='cancelled', resolved_by=:uid, resolved_at=now()
        WHERE id=:eid AND org_id=:org AND status='open'
    '''), {'uid': user.id, 'eid': emergency_id, 'org': user.org_id})
    if updated.rowcount != 1:
        db.rollback()
        error(409, 'state_changed', '通報狀態已由其他操作更新，請重新整理後確認')
    record_event(db, emergency_id, user, 'cancelled', 'open', 'cancelled')
    audit.record(db, 'sos.cancel', actor=user, target_type='emergency', target_id=emergency_id,
                 meta={'reason': body.reason, 'was_reporter': is_reporter,
                       'client_request_id': str(body.client_request_id)})
    db.commit()
    return serialize(get_one(db, user, emergency_id))

# XZ_READINESS_ROLES_20261103
@router.get(PREFIX + '/emergencies/notification-readiness')
def notification_readiness(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Counts of eligible recipients, never a delivery receipt or alert trigger."""
    check_role(user, MANAGERS)
    return {
        'channel': 'emergency_app',
        'delivery': 'web_poll_only',
        'notification_delivery_verified': False,
        'worker_dispatch_state': 'not_applicable',
        'delivery_note': '緊急 APP 的前景輪詢只能顯示事件，不代表背景通知已送達。',
    }
    # The former LINE/WebPush readiness implementation below is intentionally
    # unreachable until removed with a separately reviewed cleanup change.
    rows = db.execute(text("""
        SELECT u.role, COUNT(DISTINCT u.id) AS active,
               COUNT(DISTINCT u.id) FILTER (
                 WHERE a.linked_at IS NOT NULL AND a.is_blocked IS FALSE
               ) AS line_ready
        FROM users u
        LEFT JOIN line_accounts a ON a.user_id = u.id
        WHERE u.org_id = :org AND u.is_active IS TRUE
          AND u.role IN ('supervisor', 'director', 'admin')
        GROUP BY u.role
    """), {'org': user.org_id}).mappings().all()
    result = {role: {'active': 0, 'line_ready': 0} for role in MANAGERS}
    for row in rows:
        if row['role'] in result:
            result[row['role']] = {
                'active': int(row['active']),
                'line_ready': int(row['line_ready']),
            }
    # Keep LINE and Web Push readiness separate. A subscription only confirms
    # registration on a device; it is NOT proof of successful delivery.
    push_rows = db.execute(text("""
        SELECT u.role, COUNT(DISTINCT u.id) FILTER (
            WHERE s.is_active IS TRUE
        ) AS webpush_ready
        FROM users u
        LEFT JOIN jiaan_webpush_subscriptions s
          ON s.user_id = u.id AND s.org_id = u.org_id
        WHERE u.org_id = :org AND u.is_active IS TRUE
          AND u.role IN ('supervisor', 'director', 'admin')
        GROUP BY u.role
    """), {'org': user.org_id}).mappings().all()
    for role in result:
        result[role]['webpush_ready'] = 0
    for row in push_rows:
        if row['role'] in result:
            result[row['role']]['webpush_ready'] = int(row['webpush_ready'])
    return {
        'recipients': result,
        'new_and_60s_webpush_ready': result['supervisor']['webpush_ready'],
        '180s_webpush_ready': result['director']['webpush_ready'] + result['admin']['webpush_ready'],
        'new_and_60s_line_ready': result['supervisor']['line_ready'],
        '180s_line_ready': result['director']['line_ready'] + result['admin']['line_ready'],
        'notification_delivery_verified': False,
        'worker_dispatch_state': 'not_verified_by_this_endpoint',
        'delivery_note': '符合接收資格不等於已發送或已送達手機。',
    }


# XZ_EMERGENCY_DELIVERY_STATUS_20261103
@router.get(PREFIX + '/emergencies/{emergency_id}/delivery-status')
def emergency_delivery_status(emergency_id: uuid.UUID,
                              user: User = Depends(current_user),
                              db: Session = Depends(get_db)) -> dict:
    """Aggregate LINE request states only; never expose recipient IDs or claim handset delivery."""
    check_role(user, MANAGERS)
    get_one(db, user, emergency_id)
    raise HTTPException(
        status_code=410,
        detail={'code': 'management_line_sos_disabled',
                'message': '管理角色 LINE SOS 已停用；請以緊急 APP 內的事件狀態為準。'},
    )
    # Legacy aggregation remains unreachable for audit/diff review.
    from app.services.jiaan_emergency_delivery_summary import summarize_delivery_rows
    check_role(user, MANAGERS)
    # Restricts access to the same organization before querying notifications.
    incident = get_one(db, user, emergency_id)
    rows = db.execute(text("""
        SELECT payload->>'stage' AS stage, status, COUNT(*) AS count
        FROM notification_jobs
        WHERE org_id=:org AND source_type='jiaan_emergency'
          AND channel='line' AND payload->>'kind'='jiaan_emergency_alert'
          AND payload->>'emergency_id'=:eid
        GROUP BY payload->>'stage', status
    """), {'org': user.org_id, 'eid': str(emergency_id)}).mappings().all()
    return {
        'emergency_id': str(emergency_id),
        'incident_status': incident['status'],
        'channel': 'line',
        **summarize_delivery_rows(rows),
        'warning': 'accepted 只代表 LINE 平台已受理，不代表手機已收到；沒有通知紀錄也不表示沒有緊急事件。',
    }
