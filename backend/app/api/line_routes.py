"""LINE webhook 與模擬器端點。

webhook：先以原始 body 驗簽，驗證前不解析 JSON；寫入事件與工作後立即回 200。
模擬器（僅 LINE_MODE=mock 且非 production）：組出官方格式事件、用同一把 secret 簽章後打 webhook，
讓整條流程（驗簽→去重→排工作→處理→reply/push）在沒有 LINE 憑證時也能端到端測試。
"""

from __future__ import annotations

import json
import logging
import time

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.line import service as line_service
from app.line.client import mock_content_path
from app.line.signature import compute_signature, verify_signature
from app.models import LineAccount, LineMockOutbox, User
from app.services import audit

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_WEBHOOK_BYTES = 1024 * 1024


@router.post("/line/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    """LINE webhook 入口。"""
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail={"code": "too_large", "message": "payload too large"})
    signature = request.headers.get("x-line-signature")
    if not verify_signature(get_settings().line_channel_secret, body, signature):
        audit.record(db, "line.webhook", outcome="denied", meta={"reason": "bad_signature", "bytes": len(body)})
        db.commit()
        logger.warning("line webhook rejected: bad signature (%d bytes)", len(body))
        raise HTTPException(status_code=401, detail={"code": "bad_signature", "message": "signature mismatch"})
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "bad_json", "message": "invalid json"}) from exc
    from app.uat import check_webhook
    try:
        check_webhook(get_settings(), payload)
    except RuntimeError:
        raise HTTPException(status_code=403, detail={"code": "uat_source_not_allowed", "message": "UAT source not permitted"})
    new, duplicate = line_service.store_events(db, payload)
    logger.info("line webhook accepted: new=%d duplicate=%d", new, duplicate)
    return {"ok": True, "new": new, "duplicate": duplicate}


def _require_dev() -> None:
    if not get_settings().dev_features_enabled:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "not found"})


@router.post("/dev/line/simulate")
async def simulate(
    request: Request,
    kind: str = Form(...),
    username: str = Form(...),
    text: str | None = Form(None),
    postback: str | None = Form(None),
    redeliver_of: str | None = Form(None),
    audio: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> dict:
    """（模擬模式）以某位已綁定照服員的身分送出 LINE 事件。

    `redeliver_of` 帶入先前的 body（JSON 字串）時，會把同一事件以 isRedelivery=true 重送一次。
    """
    _require_dev()
    user = db.scalar(select(User).where(User.username == username))
    account = db.scalar(select(LineAccount).where(LineAccount.user_id == user.id)) if user else None
    line_user_id = account.line_user_id if account else f"Uunbound{username[:20]}"
    if redeliver_of:
        payload = json.loads(redeliver_of)
        for event in payload.get("events", []):
            event["deliveryContext"] = {"isRedelivery": True}
    elif kind == "audio":
        if audio is None:
            raise HTTPException(status_code=422, detail={"code": "audio_required", "message": "請附音訊檔"})
        data = await audio.read()
        message_id = str(int(time.time() * 1000))
        mock_content_path(message_id).write_bytes(data)
        payload = line_service.build_simulated_event("audio", line_user_id, message_id=message_id)
    elif kind in {"text", "follow", "unfollow", "postback"}:
        payload = line_service.build_simulated_event(kind, line_user_id, text_value=text, postback=postback)
    else:
        raise HTTPException(status_code=422, detail={"code": "bad_kind", "message": "kind 不正確"})
    body = line_service.dumps(payload)
    signature = compute_signature(get_settings().line_channel_secret, body)
    base = str(request.base_url).rstrip("/")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(f"{base}/api/line/webhook", content=body,
                                     headers={"x-line-signature": signature, "content-type": "application/json"})
    return {"status_code": response.status_code, "response": response.json(), "body": payload,
            "note": "模擬模式：事件由本機產生並以測試 channel secret 簽章，不代表真實 LINE 串接"}


@router.get("/dev/line/outbox")
def outbox(limit: int = 30, db: Session = Depends(get_db)) -> list[dict]:
    """（模擬模式）bot 將送出的 reply／push。"""
    _require_dev()
    rows = db.scalars(select(LineMockOutbox).order_by(LineMockOutbox.id.desc()).limit(max(1, min(limit, 200))))
    return [{"id": r.id, "kind": r.kind, "to": r.to, "messages": r.messages, "created_at": r.created_at.isoformat()}
            for r in rows]


@router.get("/dev/line/users")
def dev_users(db: Session = Depends(get_db)) -> list[dict]:
    """（模擬模式）可模擬的照服員（含 LINE 綁定狀態）。"""
    _require_dev()
    rows = db.execute(select(User, LineAccount).outerjoin(LineAccount, LineAccount.user_id == User.id)
                      .where(User.role == "caregiver").order_by(User.username)).all()
    return [{"username": u.username, "display_name": u.display_name,
             "line_user_id": a.line_user_id if a else None, "blocked": bool(a and a.is_blocked)} for u, a in rows]
