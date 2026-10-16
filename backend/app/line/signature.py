"""LINE webhook 簽章驗證（官方規格：以 channel secret 對原始 request body 做 HMAC-SHA256，Base64 編碼）。"""

from __future__ import annotations

import base64
import hashlib
import hmac


def compute_signature(channel_secret: str, body: bytes) -> str:
    """計算簽章。

    Args:
        channel_secret: Messaging API channel secret。
        body: 原始 request body（未經解析、未經重新編碼）。

    Returns:
        Base64 字串。
    """
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_signature(channel_secret: str, body: bytes, signature: str | None) -> bool:
    """以常數時間比較驗證 `x-line-signature`。

    Args:
        channel_secret: channel secret；空字串一律驗證失敗。
        body: 原始 request body。
        signature: header 值。

    Returns:
        是否通過。
    """
    if not channel_secret or not signature:
        return False
    return hmac.compare_digest(compute_signature(channel_secret, body), signature)
