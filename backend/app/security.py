"""密碼學小工具：加密暫存、HMAC、隨機 token、密碼雜湊。

全部只用標準庫與 cryptography，不自行發明演算法。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().data_encryption_key
    if not key:
        raise RuntimeError("DATA_ENCRYPTION_KEY 未設定，無法加密暫存資料")
    return Fernet(key.encode("ascii"))


def encrypt_json(data: Any) -> bytes:
    """把資料序列化成 JSON 後以 Fernet 加密（含時間戳與完整性驗證）。

    Args:
        data: 可 JSON 序列化的資料。

    Returns:
        加密後的位元組。
    """
    return _fernet().encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def decrypt_json(blob: bytes) -> Any:
    """解密 `encrypt_json` 的輸出。

    Args:
        blob: 加密位元組。

    Returns:
        原始資料。

    Raises:
        ValueError: 金鑰不符或資料遭竄改。
    """
    try:
        return json.loads(_fernet().decrypt(blob).decode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("加密資料無法解密（金鑰不符或已遭竄改）") from exc


def hmac_hex(value: str, purpose: str) -> str:
    """以 SECRET_KEY 對字串做 HMAC-SHA256（加上用途前綴避免跨用途重放）。

    Args:
        value: 要雜湊的字串。
        purpose: 用途標籤，例如 "session"、"deid"。

    Returns:
        十六進位字串。
    """
    key = (get_settings().secret_key or "dev-insecure-key").encode("utf-8")
    return hmac.new(key, f"{purpose}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def new_token(nbytes: int = 32) -> str:
    """產生 URL 安全的隨機 token。"""
    return secrets.token_urlsafe(nbytes)


def hash_password(password: str) -> str:
    """以 scrypt 雜湊密碼。

    Args:
        password: 明文密碼。

    Returns:
        `scrypt$n$r$p$salt$hash` 格式字串。
    """
    salt = secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        n, r, p, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(password: str, stored: str | None) -> bool:
    """驗證密碼（常數時間比較）。

    Args:
        password: 使用者輸入的明文密碼。
        stored: `hash_password` 的輸出；None 表示此帳號不能用密碼登入。

    Returns:
        是否相符。
    """
    if not stored:
        return False
    try:
        _, n, r, p, salt_b64, hash_b64 = stored.split("$")
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, base64.b64decode(hash_b64))


def sign_media_token(token_id: str, expires_at: int) -> str:
    """產生限時媒體 URL 的 token：`<token_id>.<exp>.<sig>`。

    Args:
        token_id: 隨機、不可枚舉的資源識別碼。
        expires_at: UNIX 秒數到期時間。

    Returns:
        可放在 URL path 的 token。
    """
    sig = hmac_hex(f"{token_id}.{expires_at}", "media")[:32]
    return f"{token_id}.{expires_at}.{sig}"


def verify_media_token(token: str) -> str | None:
    """驗證媒體 token；通過回傳 token_id，失敗或過期回傳 None。

    Args:
        token: `sign_media_token` 的輸出。

    Returns:
        token_id 或 None。
    """
    try:
        token_id, exp_text, sig = token.split(".")
        expires_at = int(exp_text)
    except ValueError:
        return None
    expected = hmac_hex(f"{token_id}.{expires_at}", "media")[:32]
    if not hmac.compare_digest(sig, expected):
        return None
    if expires_at < int(time.time()):
        return None
    return token_id
