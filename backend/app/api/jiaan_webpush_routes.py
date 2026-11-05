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
        raise HTTPException(409,detail='此裝置已綁定其他帳號，請先由原帳號解除')
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
