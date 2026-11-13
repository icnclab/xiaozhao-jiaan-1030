"""Fail-closed identity check for release-candidate isolated startup."""
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings


def main() -> int:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        database = connection.execute(text("SELECT current_database()" )).scalar_one()
        connection.rollback()
    if database == "ltc_clean" or not any(tag in database.lower() for tag in ("test", "acceptance", "isolated")):
        print("RESULT=STOP_UNSAFE_DATABASE_IDENTITY")
        return 1
    print(f"DATABASE={database}")
    print("RESULT=PASS_ISOLATED_DATABASE_IDENTITY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
