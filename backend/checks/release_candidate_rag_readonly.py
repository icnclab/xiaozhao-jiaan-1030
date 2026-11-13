"""Release metadata only: read aggregate RAG counts from ltc_clean, then rollback."""
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import get_engine


def main() -> int:
    with get_engine().connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        database = connection.execute(text("SELECT current_database()" )).scalar_one()
        if database != "ltc_clean":
            print("RESULT=STOP_UNEXPECTED_DATABASE")
            return 1
        row = connection.execute(text("""
            SELECT
              (SELECT count(*) FROM documents) AS documents,
              (SELECT count(*) FROM document_versions) AS versions,
              (SELECT count(*) FROM document_versions WHERE status='published') AS published_versions,
              (SELECT count(*) FROM chunks) AS chunks,
              (SELECT count(*) FROM document_versions WHERE source_url IS NOT NULL) AS source_url_versions
        """)).mappings().one()
        connection.rollback()
    print("DATABASE=ltc_clean")
    for key, value in row.items():
        print(f"{key.upper()}={value}")
    print("OFFICIAL_APPROVALS=0 (governance report; no auto-approval performed)")
    print("RESULT=PASS_READONLY_RAG_METADATA_NO_CONTENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
