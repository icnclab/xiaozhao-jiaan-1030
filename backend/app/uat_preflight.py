"""Explicit read-only commissioning checks; never sends LINE messages."""
from __future__ import annotations
import json
import urllib.request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from app.uat import verify_db_cursor, fail

def database_denial_verified(exc) -> bool:
    code = getattr(exc.orig, "sqlstate", None)
    explicit_hba = "pg_hba.conf rejects connection" in str(exc.orig)
    return code in {"28000", "42501"} or explicit_hba

def check_database(settings) -> None:
    engine = create_engine(settings.database_url, connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=5000"})
    try:
        with engine.connect() as connection:
            if connection.execute(text("SHOW transaction_read_only")).scalar_one() != "on":
                fail("UAT_READONLY_CHECK_REQUIRED")
            cursor = connection.connection.cursor()
            try:
                verify_db_cursor(cursor)
            finally:
                cursor.close()
            if connection.execute(text("SELECT has_schema_privilege(current_user,'public','CREATE')")).scalar_one():
                fail("UAT_ROLE_CAN_CREATE_SCHEMA_OBJECTS")
            rows = connection.execute(text("SELECT username,role,is_active,org_id FROM users WHERE username=ANY(:names)"), {"names":list(settings.uat_account_roles)}).mappings().all()
            actual = {row["username"]:row for row in rows}
            if any(name not in actual or not actual[name]["is_active"] or actual[name]["role"] != role for name,role in settings.uat_account_roles.items()):
                fail("UAT_ROSTER_NOT_READY")
            staff_orgs={row["org_id"] for row in rows if row["role"] in {"caregiver","supervisor","director"}}
            if len(staff_orgs) != 1:
                fail("UAT_ROSTER_ORGANIZATION_MISMATCH")
    finally:
        engine.dispose()
    # Verify actual denial, including pg_hba.conf rules. REVOKE CONNECT from a
    # role alone is insufficient when PUBLIC still has CONNECT.
    for database in ("ltc_clean", "ltc_test", "postgres"):
        other = create_engine(make_url(settings.database_url).set(database=database), connect_args={"connect_timeout":3,"options":"-c default_transaction_read_only=on"})
        try:
            with other.connect():
                fail("UAT_CAN_CONNECT_OTHER_DATABASE")
        except DBAPIError as exc:
            # libpq startup failures can omit SQLSTATE. Accept only an explicit
            # HBA rejection in that case, never timeout/password/NOLOGIN errors.
            if not database_denial_verified(exc):
                fail("UAT_DATABASE_DENIAL_NOT_VERIFIED")
        finally:
            other.dispose()

def check_line(settings) -> None:
    request=urllib.request.Request("https://api.line.me/v2/bot/channel/webhook/endpoint", headers={"Authorization":"Bearer "+settings.line_channel_access_token},method="GET")
    with urllib.request.urlopen(request,timeout=10) as response:
        value=json.load(response)
    if value.get("endpoint") != settings.public_base_url.rstrip("/")+"/api/line/webhook" or value.get("active") is not True:
        fail("UAT_WEBHOOK_ROUTE_NOT_READY")
