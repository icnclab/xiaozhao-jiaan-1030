"""Read-only schema gate for the third/fourth-round combined deployment."""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings  # noqa: E402

EXPECTED = {
    "jiaan1030_emergencies": {"id", "org_id", "created_by", "status", "category"},
    "jiaan1030_emergency_events": {"id", "emergency_id", "actor_id", "event_type"},
    "fieldtest_participants": {"org_id", "code", "user_id", "assigned_by", "assigned_at"},
    "jiaan_webpush_subscriptions": {"id", "org_id", "user_id", "endpoint_hash"},
    "jiaan_webpush_deliveries": {"id", "emergency_id", "status"},
}


def main() -> int:
    engine = create_engine(get_settings().database_url)
    failures: list[str] = []
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        database = conn.execute(text("SELECT current_database()" )).scalar_one()
        print(f"DATABASE={database}")
        if database != "ltc_clean":
            failures.append("unexpected database")
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        print(f"ALEMBIC_VERSION={version}")
        for table, required in EXPECTED.items():
            columns = set(conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:table"
            ), {"table": table}).scalars())
            missing = sorted(required - columns)
            print(f"TABLE={table};EXISTS={bool(columns)};MISSING={','.join(missing) or '-'}")
            if missing:
                failures.append(f"{table} missing {missing}")
        conn.rollback()
    if failures:
        print("RESULT=FAIL_READONLY_SCHEMA_GATE")
        for item in failures:
            print("FAIL=" + item)
        return 1
    print("RESULT=PASS_READONLY_SCHEMA_GATE_NO_WRITES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
