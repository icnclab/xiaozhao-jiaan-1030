"""Authenticated manager opt-in to background web notifications. No credential exposure."""
from __future__ import annotations
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import User
from app.services import jiaan_webpush

router=APIRouter()
STATIC = Path(__file__).resolve().parents[1] / 'static'


def manager(user: User):
    if not user.is_active or user.role not in jiaan_webpush.MANAGERS:
        raise HTTPException(403, detail='僅授權督導與主任可使用警報接收 APP')


class Subscription(BaseModel):
    endpoint: str = Field(min_length=30,max_length=2048)
    p256dh: str = Field(min_length=40,max_length=512)
    auth: str = Field(min_length=8,max_length=255)


@router.get('/jiaan1030/alert-app', include_in_schema=False)
def alert_app():
    return FileResponse(STATIC/'jiaan_alert_app.html',media_type='text/html',
                        headers={'Cache-Control':'no-store','X-Frame-Options':'DENY'})


@router.get('/jiaan1030/alert-app.js',include_in_schema=False)
def alert_app_js():
    return FileResponse(STATIC/'jiaan_alert_app.js',media_type='application/javascript',
                        headers={'Cache-Control':'no-store'})


@router.get('/jiaan1030/alert-sw.js',include_in_schema=False)
def alert_sw():
    return FileResponse(STATIC/'jiaan_alert_sw.js',media_type='application/javascript',
                        headers={'Cache-Control':'no-store','Service-Worker-Allowed':'/api/jiaan1030/'})


@router.get('/jiaan1030/alert-manifest.json',include_in_schema=False)
def manifest():
    return FileResponse(STATIC/'jiaan_alert_manifest.json',media_type='application/manifest+json')


@router.get('/jiaan1030/webpush/config')
def config(user: User=Depends(current_user)):
    manager(user)
    return {'public_key':jiaan_webpush.public_key(), 'enabled':jiaan_webpush.enabled(),
            'warning':'背景推播與鎖屏提醒受手機設定限制，不能保證持續響鈴或送達'}


@router.post('/jiaan1030/webpush/subscription')
def subscribe(body:Subscription,user:User=Depends(current_user),db:Session=Depends(get_db)):
    manager(user)
    if not jiaan_webpush.endpoint_allowed(body.endpoint):
        raise HTTPException(422,detail='不支援的推播服務位址')
    # Lookup by a keyed digest; store endpoint and browser auth keys encrypted at rest.
    try:
        endpoint_digest = jiaan_webpush.endpoint_hash(body.endpoint)
        endpoint_cipher = jiaan_webpush.encrypt_subscription_value(body.endpoint)
        p256dh_cipher = jiaan_webpush.encrypt_subscription_value(body.p256dh)
        auth_cipher = jiaan_webpush.encrypt_subscription_value(body.auth)
    except RuntimeError:
        raise HTTPException(503, detail='推播訂閱安全設定尚未就緒')
    owner=db.execute(text('SELECT user_id FROM jiaan_webpush_subscriptions WHERE endpoint_hash=:digest'),
                     {'digest':endpoint_digest}).scalar_one_or_none()
    if owner and owner!=user.id:
        raise HTTPException(409, detail={
            'code': 'subscription_owned_by_other_user',
            'message': '此裝置已綁定其他帳號，請先由原帳號解除',
        })
    db.execute(text('''
        INSERT INTO jiaan_webpush_subscriptions
           (id,user_id,org_id,endpoint,endpoint_hash,p256dh,auth,is_active)
        VALUES (:id,:uid,:org,:endpoint,:digest,:p256dh,:auth,true)
        ON CONFLICT (endpoint_hash) DO UPDATE SET
            p256dh=EXCLUDED.p256dh, auth=EXCLUDED.auth, endpoint=EXCLUDED.endpoint,
            is_active=true, updated_at=now()
    '''), {'id':uuid.uuid4(),'uid':user.id,'org':user.org_id,'endpoint':endpoint_cipher,
           'digest':endpoint_digest, 'p256dh':p256dh_cipher,'auth':auth_cipher})
    db.commit()
    return {'status':'subscribed', 'dispatch_enabled':jiaan_webpush.enabled()}


@router.delete('/jiaan1030/webpush/subscription')
def unsubscribe(body:Subscription,user:User=Depends(current_user),db:Session=Depends(get_db)):
    manager(user)
    try:
        endpoint_digest = jiaan_webpush.endpoint_hash(body.endpoint)
    except RuntimeError:
        raise HTTPException(503, detail='推播訂閱安全設定尚未就緒')
    db.execute(text('''UPDATE jiaan_webpush_subscriptions SET is_active=false, updated_at=now()
        WHERE endpoint_hash=:digest AND user_id=:uid AND org_id=:org'''),
        {'digest':endpoint_digest,'uid':user.id,'org':user.org_id})
    db.commit()
    return {'status':'unsubscribed'}


@router.get('/jiaan1030/alert-icon-{size}.png',include_in_schema=False)
def icon(size: int):
    if size not in (192,512):
        raise HTTPException(404,detail='not found')
    return FileResponse(STATIC/f'jiaan_alert_icon_{size}.png',media_type='image/png')

# XZ_SOS_STANDALONE_ROUTES_V1 - dedicated role-based SOS PWA, separate from LIFF/admin.
@router.get('/jiaan1030/sos-app/', include_in_schema=False)
def sos_standalone_app():
    return FileResponse(STATIC/'xz_sos_app.html', media_type='text/html',
                        headers={'Cache-Control':'no-store', 'X-Frame-Options':'DENY',
                                 'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; manifest-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'"})

@router.get('/jiaan1030/sos-app/app.js', include_in_schema=False)
def sos_standalone_js():
    return FileResponse(STATIC/'xz_sos_app.js', media_type='application/javascript',
                        headers={'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})

@router.get('/jiaan1030/sos-app/sw.js', include_in_schema=False)
def sos_standalone_sw():
    return FileResponse(STATIC/'xz_sos_sw.js', media_type='application/javascript',
                        headers={'Cache-Control':'no-store', 'Service-Worker-Allowed':'/api/jiaan1030/sos-app/'})

@router.get('/jiaan1030/sos-app/manifest.json', include_in_schema=False)
def sos_standalone_manifest():
    return FileResponse(STATIC/'xz_sos_manifest.json', media_type='application/manifest+json',
                        headers={'Cache-Control':'no-store'})


# XZ_SOS_SELF_PUSH_TEST_V1. Disabled by default; opt-in only on the isolated test API.
# Sends ONLY to a subscription already owned by the authenticated supervisor/director/admin.
# Does not create an SOS incident, insert a delivery row, or enable any dispatch worker.
from threading import Lock as _XZ_TestLock
from time import monotonic as _xz_monotonic
import os as _xz_os
import json as _xz_json

_xz_test_lock = _XZ_TestLock()
_xz_test_last = {}

class _XZ_SelfTestRequest(BaseModel):
    endpoint: str = Field(min_length=30, max_length=2048)

@router.post('/jiaan1030/webpush/self-test', status_code=202)
def sos_webpush_self_test(body: _XZ_SelfTestRequest, user: User=Depends(current_user), db: Session=Depends(get_db)):
    manager(user)
    if _xz_os.getenv('JIAAN_WEBPUSH_SELF_TEST', 'off').strip().lower() != 'on':
        # 403 (not 503): this is a deliberate configuration toggle, not a
        # transient system failure, so it must not be retryable and must not
        # be flattened to the generic 5xx SYSTEM_FAILURE text in
        # app/main.py's global handler -- the operator-facing reason is not
        # sensitive and the user should see it plainly instead of guessing.
        raise HTTPException(403, detail={'code': 'self_test_disabled', 'message': '此環境目前停用遠端推播測試'})
    if not jiaan_webpush.endpoint_allowed(body.endpoint):
        raise HTTPException(422, detail='不支援的推播服務位址')
    required=('JIAAN_VAPID_PUBLIC_KEY','JIAAN_VAPID_PRIVATE_KEY','JIAAN_VAPID_SUBJECT')
    if not all(_xz_os.environ.get(name) for name in required):
        raise HTTPException(503, detail='推播金鑰尚未載入')
    try:
        digest=jiaan_webpush.endpoint_hash(body.endpoint)
    except RuntimeError:
        raise HTTPException(503, detail='推播訂閱加密設定尚未就緒')
    record=db.execute(text('''SELECT endpoint,p256dh,auth FROM jiaan_webpush_subscriptions
        WHERE endpoint_hash=:digest AND user_id=:uid AND org_id=:org AND is_active=true'''),
        {'digest':digest,'uid':user.id,'org':user.org_id}).mappings().first()
    if not record:
        raise HTTPException(404, detail='這台裝置沒有屬於目前登入者的有效訂閱')
    # Per-logged-in-user throttle, one test per 90s in this single preview process.
    with _xz_test_lock:
        current=_xz_monotonic()
        key=str(user.id)
        if current-_xz_test_last.get(key,-100000) < 90:
            raise HTTPException(429, detail='請至少間隔 90 秒再測試')
        _xz_test_last[key]=current
    try:
        endpoint=jiaan_webpush.decrypt_subscription_value(record['endpoint'])
        p256dh=jiaan_webpush.decrypt_subscription_value(record['p256dh'])
        auth=jiaan_webpush.decrypt_subscription_value(record['auth'])
    except Exception:
        raise HTTPException(503, detail='推播訂閱資料無法解密')
    if endpoint!=body.endpoint or not jiaan_webpush.endpoint_allowed(endpoint):
        raise HTTPException(403, detail='裝置訂閱驗證未通過')
    pem_path=(Path(__file__).resolve().parents[3]
              /'deploy'/'fieldtest'/'.local_webpush_secrets'/'vapid_private.pem')
    if not pem_path.is_file():
        raise HTTPException(503, detail='VAPID 金鑰檔案不存在')
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        file_key=load_pem_private_key(pem_path.read_bytes(),password=None)
        env_key=load_pem_private_key(_xz_os.environ['JIAAN_VAPID_PRIVATE_KEY'].encode('utf-8'),password=None)
        if file_key.private_numbers()!=env_key.private_numbers():
            raise HTTPException(503, detail='VAPID 金鑰不一致')
    except HTTPException:
        raise
    except (ValueError, TypeError, OSError, UnicodeError, KeyError):
        raise HTTPException(503, detail='VAPID 金鑰格式錯誤')
    from pywebpush import webpush, WebPushException
    payload={'title':'小照｜非緊急遠端推播測試',
             'body':'由伺服器送出的測試通知，沒有建立緊急事件。',
             'emergency_id':'non-emergency-test','stage':'self-test',
             'url':'/api/jiaan1030/sos-app/'}
    try:
        webpush(subscription_info={'endpoint':endpoint,'keys':{'p256dh':p256dh,'auth':auth}},
                data=_xz_json.dumps(payload,ensure_ascii=False),
                vapid_private_key=str(pem_path),
                vapid_claims={'sub':_xz_os.environ['JIAAN_VAPID_SUBJECT']},
                headers={'Urgency':'normal'},ttl=90,timeout=8)
    except WebPushException as exc:
        code=getattr(getattr(exc,'response',None),'status_code',None)
        # Do not expose endpoint, VAPID keys, or response body.
        raise HTTPException(502, detail='推播服務拒絕測試通知'+(f'（HTTP {code}）' if code else ''))
    except Exception:
        raise HTTPException(502, detail='測試推播發送失敗')
    return {'status':'provider_accepted','note':'推播服務接受請求，不等於手機已收到。請實際檢查裝置。'}
