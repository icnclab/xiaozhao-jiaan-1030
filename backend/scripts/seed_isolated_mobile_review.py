"""2026-11-13: seed a handful of synthetic test accounts into the ISOLATED
`ltc_test` database only, for mobile-browser review of the SOS PWA candidate
build. Hard-refuses to run against anything other than `ltc_test` -- this
must never be pointed at `ltc_clean`.

Usage (from backend/, with DATABASE_URL overridden to TEST_DATABASE_URL):
    DATABASE_URL=$TEST_DATABASE_URL .venv/Scripts/python.exe scripts/seed_isolated_mobile_review.py
"""
from __future__ import annotations
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.auth import set_password
from app.config import get_settings
from app.db import session_scope
from app.models import Organization, User

ROLES = ["caregiver", "supervisor", "director", "admin"]


def main() -> None:
    settings = get_settings()
    url = settings.database_url
    if "ltc_test" not in url or "ltc_clean" in url:
        raise SystemExit(f"REFUSING: DATABASE_URL must be the isolated ltc_test database, got: {url}")

    out_lines = ["# 隔離測試帳號（ltc_test），僅供手機瀏覽器驗收 SOS PWA 候選版使用，非正式帳號\n"]
    with session_scope() as session:
        org = session.scalar(select(Organization).where(Organization.code == "MOBILEQA"))
        if org is None:
            org = Organization(code="MOBILEQA", name="〔隔離測試〕手機驗收虛構機構", facility_type="home")
            session.add(org)
            session.flush()
        for role in ROLES:
            username = f"mobileqa_{role}"
            user = session.scalar(select(User).where(User.username == username))
            # NOTE: 2026-11-13 fix -- pytest now runs against its own
            # dedicated ltc_pytest database (see tests/conftest.py and
            # docs/20261113_SOS隔離程序安全與測試DB防護.md), never ltc_test,
            # so a pytest run no longer wipes these accounts. Keep the SAME password
            # when the account is recreated so credentials already handed to
            # the user stay valid; only generate a new one the very first time.
            password = secrets.token_urlsafe(9)
            if user is None:
                user = User(org_id=org.id, username=username, display_name=f"隔離測試-{role}", role=role, is_active=True)
                session.add(user)
                session.flush()
                set_password(user, password)
            else:
                password = "(未變更，沿用既有密碼)"
            out_lines.append(f"{role}: username={username} password={password}\n")
    out_path = Path(__file__).resolve().parents[2] / "run" / "mobile_qa_accounts.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(out_lines), encoding="utf-8")
    print(f"Seeded {len(ROLES)} isolated test accounts into ltc_test. Credentials: {out_path}")


if __name__ == "__main__":
    main()
