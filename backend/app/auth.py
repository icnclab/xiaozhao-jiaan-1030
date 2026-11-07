"""身分驗證與授權。

- LIFF：前端只送 ID token，後端呼叫 LINE 官方驗證端點取得 `sub`（LINE userId）；
  **不接受前端傳入的 user_id 或角色**。
- 後台：帳號密碼（scrypt）。
- session token 只存 HMAC 雜湊；每個請求都重新讀取使用者角色與機構。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import timedelta

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuthSession, BindingCode, LineAccount, User
from app.security import hash_password, hmac_hex, new_token
from app.services import audit, jobs
from app.services.jiaan_line_binding_policy import BINDABLE_ROLES, requires_verified_real_line

LINE_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"
DEV_TOKEN_PREFIX = "dev:"


class AuthError(Exception):
    """驗證失敗。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LineIdentity:
    """驗證後的 LINE 身分。"""

    line_user_id: str
    display_name: str | None
    dev: bool


def verify_liff_id_token(id_token: str) -> LineIdentity:
    """驗證 LIFF ID token。

    Args:
        id_token: `liff.getIDToken()` 取得的 token；mock 模式可用 `dev:<LINE userId>`。

    Returns:
        LINE 身分。

    Raises:
        AuthError: 驗證失敗。
    """
    settings = get_settings()
    if id_token.startswith(DEV_TOKEN_PREFIX):
        if not settings.dev_features_enabled:
            raise AuthError("dev_disabled", "模擬登入已停用")
        line_user_id = id_token[len(DEV_TOKEN_PREFIX):]
        if not line_user_id.startswith("U") or len(line_user_id) > 64:
            raise AuthError("invalid_token", "模擬 token 格式錯誤")
        return LineIdentity(line_user_id=line_user_id, display_name=None, dev=True)
    if not settings.line_login_channel_id:
        raise AuthError("not_configured", "未設定 LINE_LOGIN_CHANNEL_ID，無法驗證 LIFF 身分")
    try:
        response = httpx.post(LINE_VERIFY_URL, data={"id_token": id_token,
                                                     "client_id": settings.line_login_channel_id}, timeout=10)
    except httpx.HTTPError as exc:
        raise AuthError("verify_unreachable", "暫時無法連線 LINE 驗證服務") from exc
    if response.status_code != 200:
        raise AuthError("invalid_token", "LINE 身分驗證失敗，請重新開啟頁面")
    claims = response.json()
    if str(claims.get("aud")) != settings.line_login_channel_id or int(claims.get("exp", 0)) < time.time():
        raise AuthError("invalid_token", "LINE 身分驗證失敗")
    from app.uat import identity_allowed
    if not identity_allowed(settings, str(claims["sub"])):
        raise AuthError("uat_identity_not_allowed", "UAT identity not permitted")
    return LineIdentity(line_user_id=str(claims["sub"]), display_name=claims.get("name"), dev=False)


def issue_session(session: Session, user: User, kind: str) -> str:
    """發 session token（回傳明文一次，DB 只存雜湊）。"""
    from app.uat import account_allowed
    if not account_allowed(get_settings(), user):
        raise AuthError("uat_account_not_allowed", "UAT account not permitted")
    token = new_token(32)
    session.add(AuthSession(user_id=user.id, token_hash=hmac_hex(token, "session"), kind=kind,
                            expires_at=jobs.utcnow() + timedelta(hours=get_settings().session_ttl_hours)))
    return token


def find_line_user(session: Session, identity: LineIdentity) -> User | None:
    """找出已綁定此 LINE 身分的啟用帳號。"""
    account = session.scalar(select(LineAccount).where(LineAccount.line_user_id == identity.line_user_id))
    if account is None:
        return None
    user = session.get(User, account.user_id)
    from app.uat import account_allowed
    if user and not account_allowed(get_settings(), user):
        raise AuthError("uat_account_not_allowed", "UAT account not permitted")
    return user if user and user.is_active else None


def bind_line_account(session: Session, identity: LineIdentity, code: str) -> User:
    """以一次性綁定碼綁定 LINE 身分與系統帳號。

    Raises:
        AuthError: 綁定碼無效、已使用、過期，或此 LINE 已綁其他帳號。
    """
    code_hash = hmac_hex(code.strip().upper(), "binding")
    binding = session.scalar(select(BindingCode).where(BindingCode.code_hash == code_hash).with_for_update())
    if binding is None or binding.used_at is not None or binding.expires_at < jobs.utcnow():
        audit.record(session, "auth.bind", outcome="denied", meta={"reason": "invalid_code"})
        session.commit()
        raise AuthError("invalid_code", "綁定碼無效或已過期，請向督導索取新的綁定碼")
    user = session.get(User, binding.user_id)
    if user is None or not user.is_active or user.role not in BINDABLE_ROLES:
        raise AuthError("invalid_code", "帳號無法使用此綁定碼")
    from app.uat import account_allowed
    if not account_allowed(get_settings(), user):
        raise AuthError("uat_account_not_allowed", "UAT account not permitted")
    # XZ_MANAGER_LINE_BINDING_20261103
    if requires_verified_real_line(user.role) and identity.dev:
        raise AuthError("real_line_required", "督導、主任及管理員須以本人真實 LINE 完成綁定")
    existing = session.scalar(select(LineAccount).where(LineAccount.line_user_id == identity.line_user_id))
    if existing and existing.user_id != user.id:
        raise AuthError("already_bound", "這個 LINE 帳號已綁定其他人員，請聯絡管理員")
    mine = session.scalar(select(LineAccount).where(LineAccount.user_id == user.id))
    if requires_verified_real_line(user.role) and mine and mine.line_user_id != identity.line_user_id:
        raise AuthError("line_rebind_requires_unbind", "此人員已有 LINE 綁定，請先由授權管理者解除原綁定")
    if mine is None:
        session.add(LineAccount(user_id=user.id, line_user_id=identity.line_user_id, followed_at=jobs.utcnow()))
    else:
        mine.line_user_id = identity.line_user_id
        mine.is_blocked = False
    binding.used_at = jobs.utcnow()
    audit.record(session, "auth.bind", actor=user, target_type="user", target_id=user.id)
    return user


def create_binding_code(session: Session, actor: User, user: User) -> str:
    """產生綁定碼（8 碼，易輸入；DB 只存雜湊，7 天有效）。"""
    from app.uat import account_allowed
    if not account_allowed(get_settings(), user):
        raise AuthError("uat_account_not_allowed", "UAT account not permitted")
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    import secrets

    code = "".join(secrets.choice(alphabet) for _ in range(8))
    session.add(BindingCode(user_id=user.id, code_hash=hmac_hex(code, "binding"),
                            expires_at=jobs.utcnow() + timedelta(days=7)))
    audit.record(session, "auth.binding_code", actor=actor, target_type="user", target_id=user.id)
    return code


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """FastAPI 相依：取得目前使用者（每次請求重讀角色與機構）。"""
    token = _bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "請先登入"})
    auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hmac_hex(token, "session")))
    if auth_session is None or auth_session.revoked_at is not None or auth_session.expires_at < jobs.utcnow():
        raise HTTPException(status_code=401, detail={"code": "session_expired", "message": "登入已逾時，請重新登入"})
    user = db.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail={"code": "inactive", "message": "帳號已停用"})
    request.state.auth_session_id = auth_session.id
    from app.uat import account_allowed
    if not account_allowed(get_settings(), user):
        raise HTTPException(status_code=403, detail={"code": "uat_account_not_allowed", "message": "UAT account not permitted"})
    return user


def require_roles(*roles: str):
    """FastAPI 相依產生器：限定角色。"""

    def _dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "沒有權限執行此操作"})
        return user

    return _dependency


def deny_not_found(db: Session, user: User, target_type: str, target_id: uuid.UUID | str) -> HTTPException:
    """跨機構或越權存取：寫稽核並回 404（不洩漏資源是否存在）。"""
    audit.record(db, "access_denied", actor=user, target_type=target_type, target_id=target_id, outcome="denied")
    db.commit()
    return HTTPException(status_code=404, detail={"code": "not_found", "message": "找不到資料"})


def set_password(user: User, password: str) -> None:
    """設定密碼（至少 10 字元）。"""
    if len(password) < 10:
        raise AuthError("weak_password", "密碼至少 10 個字元")
    user.password_hash = hash_password(password)
