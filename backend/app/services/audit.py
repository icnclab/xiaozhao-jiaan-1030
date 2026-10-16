"""稽核紀錄寫入。meta 只放 ID、計數與代碼，不放未遮罩文字、token 或金鑰。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog

_FORBIDDEN_META_KEYS = {"text", "question", "raw", "token", "password", "secret", "id_token", "body"}


def record(
    session: Session,
    action: str,
    *,
    actor: Any | None = None,
    org_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: Any | None = None,
    outcome: str = "ok",
    meta: dict[str, Any] | None = None,
) -> None:
    """寫一筆稽核紀錄（加入目前交易，由呼叫端 commit）。

    Args:
        session: ORM session。
        action: 動作名稱，例如 qa.ask、case.reply、doc.publish、access_denied。
        actor: 執行者 User（可為 None，例如 webhook）。
        org_id: 機構 ID；未給時取 actor 的機構。
        target_type: 目標類型。
        target_id: 目標 ID。
        outcome: ok、denied 或 error。
        meta: 其他非敏感資訊。

    Raises:
        ValueError: meta 含禁止的鍵（防止誤把內容寫進稽核）。
    """
    meta = dict(meta or {})
    bad = _FORBIDDEN_META_KEYS & set(meta)
    if bad:
        raise ValueError(f"稽核 meta 不可包含敏感欄位：{sorted(bad)}")
    session.add(
        AuditLog(
            org_id=org_id or (actor.org_id if actor is not None else None),
            actor_id=actor.id if actor is not None else None,
            actor_role=actor.role if actor is not None else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            outcome=outcome,
            meta=meta,
        )
    )
