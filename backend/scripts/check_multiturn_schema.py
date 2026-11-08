"""Read-only schema compatibility check for multi-turn Interaction support."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


EXPECTED = {
    "qa_items": {"id", "org_id", "user_id", "conversation_id", "client_request_id", "question_masked"},
    "service_interactions": {
        "id", "org_id", "owner_id", "start_request_id", "created_at", "ended_at",
    },
    "interaction_read_grants": {
        "id", "interaction_id", "viewer_id", "approved_by", "responsible", "read_approved", "created_at",
    },
}


def check(url: str) -> dict:
    engine = create_engine(
        url,
        connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=5000"},
    )
    try:
        with engine.connect() as connection:
            if connection.execute(text("SHOW transaction_read_only")).scalar_one() != "on":
                raise RuntimeError("READ_ONLY_REQUIRED")
            inspector = inspect(connection)
            tables = set(inspector.get_table_names(schema="public"))
            details = {}
            compatible = True
            for table, required in EXPECTED.items():
                actual = (
                    {column["name"] for column in inspector.get_columns(table)}
                    if table in tables else set()
                )
                missing = sorted(required - actual)
                details[table] = {"present": table in tables, "missing_columns": missing}
                compatible = compatible and table in tables and not missing
            version = None
            if "alembic_version" in tables:
                version = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
            return {"compatible": compatible, "alembic_version": version, "tables": details}
    finally:
        engine.dispose()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url")
    parser.add_argument("--uat-env-file")
    args = parser.parse_args(argv)
    if bool(args.database_url) == bool(args.uat_env_file):
        parser.error("provide exactly one of --database-url or --uat-env-file")
    if args.uat_env_file:
        os.environ["LTC_PROFILE"] = "uat"
        os.environ["LTC_UAT_ENV_FILE"] = str(Path(args.uat_env_file).resolve())
        from app.config import get_settings

        get_settings.cache_clear()
        url = get_settings().database_url
    else:
        url = args.database_url
    result = check(url)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["compatible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
