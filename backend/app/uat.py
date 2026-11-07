"""Fail-closed UAT policy. No credentials, network or DB writes at import time."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy.engine import make_url
from dotenv import dotenv_values

PROTECTED_FIELDS = (
    "line_login_channel_id", "liff_id", "line_channel_secret", "line_channel_access_token",
    "secret_key", "data_encryption_key", "internal_health_token",
)

def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def canonical_origin(value: str) -> str:
    parsed = urlsplit(value)
    port = parsed.port
    suffix = "" if port in (None, 443) else ":" + str(port)
    return parsed.scheme.lower() + "://" + (parsed.hostname or "").lower() + suffix

def fail(code: str):
    raise RuntimeError(code)

def read_values(path: str) -> dict[str, str]:
    p = Path(path)
    if not p.is_absolute() or p.name == ".env" or not p.is_file():
        fail("UAT_DEDICATED_ABSOLUTE_ENV_FILE_REQUIRED")
    values = dotenv_values(p, interpolate=False)
    if any(v is None or "${" in v for v in values.values()):
        fail("UAT_ENV_INTERPOLATION_OR_EMPTY_ASSIGNMENT_FORBIDDEN")
    return {k.lower(): v for k, v in values.items()}

def validate_settings(s) -> None:
    if s.app_env != "uat" or s.line_mode != "real":
        fail("UAT_REAL_LOGIN_PROFILE_REQUIRED")
    db = make_url(s.database_url)
    if db.database != "ltc_demo" or db.username != "ltc_uat_app" or db.drivername != "postgresql+psycopg":
        fail("UAT_DATABASE_OR_ROLE_FORBIDDEN")
    if db.query:
        fail("UAT_DATABASE_OVERRIDE_FORBIDDEN")
    if not db.password or db.password.startswith("REPLACE_") or not db.host:
        fail("UAT_DATABASE_CREDENTIAL_REQUIRED")
    origin = urlsplit(s.public_base_url)
    if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
        or origin.port not in (None, 443) or origin.path not in ("", "/") or origin.query or origin.fragment
        or origin.hostname in {"localhost", "127.0.0.1"} or origin.hostname.endswith(".invalid")):
        fail("UAT_DEDICATED_HTTPS_ORIGIN_REQUIRED")
    data = Path(s.data_dir).resolve()
    if not Path(s.data_dir).is_absolute() or data.name != "data_demo":
        fail("UAT_DATA_DIRECTORY_FORBIDDEN")
    bp = Path(s.uat_production_fingerprints_file)
    if not bp.is_absolute() or not bp.is_file():
        fail("UAT_PRODUCTION_FINGERPRINT_BASELINE_REQUIRED")
    try:
        baseline = json.loads(bp.read_text(encoding="utf-8"))
        hashes = baseline["fields"]
        db_hash = baseline["database_password"]
        if len(db_hash) != 64 or any(c not in "0123456789abcdef" for c in db_hash):
            fail("UAT_BASELINE_INVALID")
        if fingerprint(db.password) == db_hash:
            fail("UAT_SHARED_DATABASE_PASSWORD_FORBIDDEN")
        if baseline["version"] != 1 or not baseline["origins"] or not baseline["data_dirs"]:
            fail("UAT_BASELINE_INVALID")
        for key in PROTECTED_FIELDS:
            h = hashes[key]
            if len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
                fail("UAT_BASELINE_INVALID")
            value = getattr(s, key)
            if not value or value != value.strip() or value.startswith("REPLACE_") or fingerprint(value) == h:
                fail("UAT_MISSING_OR_SHARED_" + key.upper())
        if fingerprint(canonical_origin(s.public_base_url)) in baseline["origins"]:
            fail("UAT_PRODUCTION_ORIGIN_FORBIDDEN")
        if fingerprint(str(data)) in baseline["data_dirs"]:
            fail("UAT_PRODUCTION_DATA_DIRECTORY_FORBIDDEN")
    except (OSError, ValueError, KeyError, TypeError):
        fail("UAT_BASELINE_INVALID")
    if len(s.secret_key) < 32 or len(s.internal_health_token) < 32:
        fail("UAT_NEW_APPLICATION_KEYS_REQUIRED")
    from cryptography.fernet import Fernet
    try:
        Fernet(s.data_encryption_key.encode("ascii"))
    except (ValueError, UnicodeError):
        fail("UAT_NEW_ENCRYPTION_KEY_REQUIRED")
    if not s.line_login_channel_id.isdigit() or not s.liff_id.startswith(s.line_login_channel_id + "-"):
        fail("UAT_LIFF_CHANNEL_MISMATCH")
    import re
    if not s.uat_line_user_ids or any(not re.fullmatch(r"U[0-9a-fA-F]{32}", x) for x in s.uat_line_user_ids):
        fail("UAT_EXPLICIT_TEST_IDENTITIES_REQUIRED")
    if not s.uat_account_roles or not {"caregiver", "supervisor", "director"}.issubset(set(s.uat_account_roles.values())):
        fail("UAT_THREE_ROLE_ROSTER_REQUIRED")
    if any(v not in {"caregiver", "supervisor", "director", "admin"} for v in s.uat_account_roles.values()):
        fail("UAT_ROSTER_ROLE_INVALID")
    if s.uat_outbound_mode not in {"blocked", "allowlist"}:
        fail("UAT_OUTBOUND_POLICY_INVALID")

def identity_allowed(s, line_user_id: str) -> bool:
    return not s.is_uat or line_user_id in s.uat_line_user_ids

def account_allowed(s, user) -> bool:
    return not s.is_uat or (user.is_active and s.uat_account_roles.get(user.username) == user.role)

def check_webhook(s, payload: dict) -> None:
    if not s.is_uat:
        return
    if not isinstance(payload, dict):
        fail("UAT_WEBHOOK_PAYLOAD_INVALID")
    events = payload.get("events")
    if not isinstance(events, list):
        fail("UAT_WEBHOOK_PAYLOAD_INVALID")
    for event in events:
        source = event.get("source", {}) if isinstance(event, dict) else {}
        if source.get("type") != "user" or not identity_allowed(s, source.get("userId", "")):
            fail("UAT_WEBHOOK_SOURCE_NOT_ALLOWED")

def push_allowed(s, recipient: str) -> bool:
    return not s.is_uat or (s.uat_outbound_mode == "allowlist" and recipient in s.uat_line_user_ids)

def messages_allowed(s, messages) -> bool:
    if not s.is_uat:
        return True
    import re
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for child in value.values():
                yield from strings(child)
        elif isinstance(value, list):
            for child in value:
                yield from strings(child)
    for value in strings(messages):
        for raw in re.findall(r"https?://[^\s<>]+", value):
            url = urlsplit(raw.rstrip(".,;)]}"))
            origin = urlsplit(s.public_base_url)
            own = url.scheme == "https" and url.netloc == origin.netloc and not url.username and not url.password
            liff = url.scheme == "https" and url.netloc == "liff.line.me" and url.path.split("/")[1:2] == [s.liff_id]
            if not (own or liff):
                return False
    return True

def request_allowed(s, host: str, origin: str | None, path: str, method: str) -> bool:
    if not s.is_uat:
        return True
    expected = urlsplit(s.public_base_url).netloc
    local_read = host in {"localhost", "127.0.0.1", "127.0.0.1:8151", "localhost:8151"} and method == "GET" and path in {"/api/healthz", "/api/config/public"}
    return (host == expected or local_read) and (not origin or origin.rstrip("/") == s.public_base_url.rstrip("/"))

def verify_db_cursor(cursor) -> None:
    cursor.execute("""SELECT current_database(), current_user,
      (SELECT coalesce(bool_or(rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls),false)
       FROM pg_roles WHERE rolname=current_user OR pg_has_role(current_user,oid,'MEMBER'))""")
    db, role, dangerous = cursor.fetchone()
    if db != "ltc_demo" or role != "ltc_uat_app" or dangerous:
        fail("UAT_DATABASE_RUNTIME_GUARD_REJECTED")
