"""身分與公開設定 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    AuthError,
    bind_line_account,
    current_user,
    find_line_user,
    issue_session,
    verify_liff_id_token,
)
from app.config import get_settings
from app.db import get_db
from app.models import AuthSession, Organization, User
from app.security import verify_password
from app.services import audit, jobs
from app.services.qa_policy import DEFAULT_POLICY
from app.services.transcripts import CONSENT_TEXT, CONSENT_TEXT_VERSION
from app.services.wake import wake_words

router = APIRouter()


class LiffLoginIn(BaseModel):
    id_token: str = Field(min_length=5, max_length=4096)


class LiffBindIn(LiffLoginIn):
    binding_code: str = Field(min_length=6, max_length=16)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


def user_out(db: Session, user: User) -> dict:
    """使用者資訊。"""
    org = db.get(Organization, user.org_id)
    return {"id": str(user.id), "display_name": user.display_name, "role": user.role, "username": user.username,
            "org": {"id": str(org.id), "name": org.name, "facility_type": org.facility_type} if org else None}


def _auth_http(exc: AuthError, status: int = 401) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)})


@router.post("/auth/liff")
def liff_login(body: LiffLoginIn, db: Session = Depends(get_db)) -> dict:
    """以 LIFF ID token 登入；未綁定回 needs_binding。"""
    try:
        identity = verify_liff_id_token(body.id_token)
    except AuthError as exc:
        raise _auth_http(exc) from exc
    user = find_line_user(db, identity)
    if user is None:
        return {"status": "needs_binding", "dev": identity.dev}
    token = issue_session(db, user, "dev" if identity.dev else "liff")
    audit.record(db, "auth.liff_login", actor=user, meta={"dev": identity.dev})
    db.commit()
    return {"status": "ok", "session_token": token, "user": user_out(db, user), "dev": identity.dev}


@router.post("/auth/liff/bind")
def liff_bind(body: LiffBindIn, db: Session = Depends(get_db)) -> dict:
    """以綁定碼綁定 LINE 身分後登入。"""
    try:
        identity = verify_liff_id_token(body.id_token)
        user = bind_line_account(db, identity, body.binding_code)
    except AuthError as exc:
        db.rollback()
        raise _auth_http(exc, 400 if exc.code != "invalid_token" else 401) from exc
    token = issue_session(db, user, "dev" if identity.dev else "liff")
    db.commit()
    return {"status": "ok", "session_token": token, "user": user_out(db, user), "dev": identity.dev}


@router.post("/auth/login")
def web_login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """後台帳密登入（照服員不可登入後台）。"""
    user = db.scalar(select(User).where(User.username == body.username.strip()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        audit.record(db, "auth.login", outcome="denied", meta={"reason": "bad_credentials"})
        db.commit()
        raise HTTPException(status_code=401, detail={"code": "bad_credentials", "message": "帳號或密碼錯誤"})
    if user.role not in {"supervisor", "director", "admin"}:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "後台僅限督導與管理員"})
    token = issue_session(db, user, "web")
    audit.record(db, "auth.login", actor=user)
    db.commit()
    return {"status": "ok", "session_token": token, "user": user_out(db, user)}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    """登出：撤銷目前 session。"""
    auth_session = db.get(AuthSession, request.state.auth_session_id)
    if auth_session:
        auth_session.revoked_at = jobs.utcnow()
    db.commit()


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """目前使用者。"""
    return user_out(db, user)


@router.get("/config/public")
def public_config() -> dict:
    """前端所需的公開設定（不含任何密鑰）。"""
    settings = get_settings()
    return {
        "line_mode": settings.line_mode,
        "liff_id": settings.liff_id,
        "dev_features": settings.dev_features_enabled,
        "modes": settings.provider_modes(),
        "limits": {"question_max_sec": settings.question_max_sec,
                   "conversation_max_sec": settings.conversation_max_sec,
                   "max_upload_mb": settings.max_upload_mb},
        "consent_text": CONSENT_TEXT,
        "consent_text_version": CONSENT_TEXT_VERSION,
        "qa_policy_version": DEFAULT_POLICY.version,
        "bot_name": settings.bot_name,
        "wake_words": wake_words(),
    }
