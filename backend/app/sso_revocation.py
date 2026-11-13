"""SSO/session revocation extension using the REAL database-backed session model.

The project authenticates with opaque AuthSession tokens, not JWT.
Do not introduce a second JWT login route or a fallback secret here.
Call revoke_user_sessions from an authorized admin action in the same transaction.
"""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.models import AuthSession, User


def revoke_user_sessions(db: Session, user_id: UUID, *, deactivate: bool = False) -> int:
    """Revoke all live sessions for a user; caller owns commit/rollback.

    Intended for a verified administrator-only action. Not an HTTP endpoint.
    ``deactivate=True`` additionally blocks new logins via existing auth.py.
    """
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("user_not_found")
    if deactivate:
        user.is_active = False
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    return int(result.rowcount or 0)
