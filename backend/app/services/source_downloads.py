"""Five-minute download capabilities; one use persisted in the existing audit log."""
import base64
import hashlib
import hmac
import json
import secrets
import time

from sqlalchemy import text

from app.security import hmac_hex


def issue(user_id: str, version_id: str, file_path: str) -> str:
    payload = {"user": user_id, "version": version_id,
               "file": hashlib.sha256(file_path.encode()).hexdigest(),
               "exp": int(time.time()) + 300, "nonce": secrets.token_hex(16)}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return encoded + "." + hmac_hex(encoded, "source-download-v1")


def verify(ticket: str) -> dict:
    try:
        if len(ticket) > 2048:
            raise ValueError()
        encoded, signature = ticket.split(".")
        if not hmac.compare_digest(signature, hmac_hex(encoded, "source-download-v1")):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if not isinstance(payload["exp"], int) or not int(time.time()) < payload["exp"] <= int(time.time()) + 300:
            raise ValueError()
        if len(payload["nonce"]) != 32:
            raise ValueError()
        int(payload["nonce"], 16)
        return payload
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ValueError("Invalid or expired download link") from exc


def claim(db, nonce: str) -> None:
    # Transaction-scoped lock serializes redemption across API processes.
    lock_id = int.from_bytes(hashlib.sha256(nonce.encode()).digest()[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
    used = db.scalar(text("SELECT id FROM audit_logs WHERE action='source.download' "
                          "AND meta->>'download_nonce'=:nonce LIMIT 1"), {"nonce": nonce})
    if used is not None:
        raise ValueError("Download link already used")
