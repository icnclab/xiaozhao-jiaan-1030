"""唯讀檢查：評估 migration 0003/0004 對正式資料庫（ltc_clean）既有結構的相容性。

只開 READ ONLY 交易、只查 information_schema / pg_catalog 等結構中繼資料與聚合統計（COUNT/MAX），
不 SELECT 任何個案內容欄位（fields_json 內容、summary_masked 文字等），結束一律 ROLLBACK，絕不 COMMIT。
不執行任何 CREATE/ALTER/INSERT/UPDATE/DELETE，不呼叫 alembic upgrade。

用法（本機 PowerShell）：
    backend\\.venv\\Scripts\\python.exe backend\\checks\\jiaan1030_prod_migration_readonly_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine, text  # noqa: E402
from app.config import get_settings  # noqa: E402


def _cols(conn, table: str, schema: str = "public") -> list[dict]:
    rows = conn.execute(text(
        "SELECT column_name, data_type, character_maximum_length, is_nullable, column_default "
        "FROM information_schema.columns WHERE table_schema = :schema AND table_name = :table "
        "ORDER BY ordinal_position"
    ), {"schema": schema, "table": table}).mappings().all()
    return [dict(r) for r in rows]


def _exists(conn, name: str, schema: str = "public", kind: str = "table") -> bool:
    if kind == "schema":
        row = conn.execute(text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :n"),
                           {"n": name}).first()
        return row is not None
    row = conn.execute(text(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = :schema AND table_name = :name"
    ), {"schema": schema, "name": name}).first()
    return row is not None


def main() -> int:
    engine = create_engine(get_settings().database_url)
    findings: list[str] = []
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))

        # ── alembic_version 現況 ──────────────────────────────────────
        version = None
        if _exists(conn, "alembic_version"):
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            print(f"CURRENT_ALEMBIC_VERSION={version}")
            if version not in (None, "0001", "0002_quality_feedback"):
                findings.append(f"alembic_version 目前是 {version}，不是本專案已知的 0001/0002，"
                                 "套用 0003/0004 前請先確認這是否為預期鏈。")
        else:
            print("CURRENT_ALEMBIC_VERSION=<alembic_version table 不存在>")
            findings.append("alembic_version 表不存在：資料庫結構從未被 alembic 追蹤過，"
                             "直接 upgrade head 會嘗試依序跑 0001→0002→0003→0004，"
                             "若 0001/0002 的物件已用其他方式手動建立，將會因物件已存在而失敗。")

        # ── 0002 的 rag_quality 結構是否已存在（只在 alembic_version 還落後於 0002 時才算風險）──
        schema_exists = _exists(conn, "rag_quality", kind="schema")
        print(f"RAG_QUALITY_SCHEMA_EXISTS={schema_exists}")
        if schema_exists and version in (None, "0001"):
            findings.append("schema rag_quality 已存在，但 alembic_version 顯示還沒跑到 0002_quality_feedback："
                             "重新 upgrade 時 0002 的 CREATE SCHEMA/CREATE TABLE 會因物件已存在而失敗，"
                             "需要先確認 0002 是否其實已手動套用、只是未被 alembic 標記。")

        # ── jiaan1030_service_forms 現況 ──────────────────────────────
        forms_exists = _exists(conn, "jiaan1030_service_forms")
        print(f"JIAAN1030_SERVICE_FORMS_EXISTS={forms_exists}")
        if forms_exists:
            cols = _cols(conn, "jiaan1030_service_forms")
            print("JIAAN1030_SERVICE_FORMS_COLUMNS=" + ",".join(c["column_name"] for c in cols))
            col_names = {c["column_name"] for c in cols}
            for required in ("code", "title", "fields_json", "reviewed"):
                if required not in col_names:
                    findings.append(f"jiaan1030_service_forms 缺少欄位 {required}，"
                                     "與 migration 0003 假設的既有結構不符，需先核對。")
            if "schema_status" in col_names:
                findings.append("jiaan1030_service_forms 已有 schema_status 欄位："
                                 "migration 0003 的 ADD COLUMN IF NOT EXISTS 會是無害的 no-op，可安全重跑。")
            code_type = next((c for c in cols if c["column_name"] == "code"), None)
            if code_type and code_type.get("character_maximum_length") and code_type["character_maximum_length"] < 20:
                findings.append(f"code 欄位目前長度上限為 {code_type['character_maximum_length']}，"
                                 "小於 migration 假設的 20，需確認既有程式與未來 BA/GA/SC 代碼是否相容。")
            max_len = conn.execute(text("SELECT MAX(length(code)) FROM jiaan1030_service_forms")).scalar()
            print(f"JIAAN1030_SERVICE_FORMS_MAX_CODE_LEN={max_len}")
            if max_len and max_len > 20:
                findings.append(f"既有 jiaan1030_service_forms 已有長度 {max_len} 的 code 值，"
                                 "超過 migration 假設的 VARCHAR(20)，正式套用前必須先處理（不可直接跑 migration）。")
            null_counts = conn.execute(text(
                "SELECT COUNT(*) FILTER (WHERE title IS NULL) AS title_null, "
                "COUNT(*) FILTER (WHERE fields_json IS NULL) AS fields_null, "
                "COUNT(*) FILTER (WHERE reviewed IS NULL) AS reviewed_null, "
                "COUNT(*) AS total FROM jiaan1030_service_forms"
            )).mappings().first()
            print(f"JIAAN1030_SERVICE_FORMS_NULL_CHECK={dict(null_counts)}")
        else:
            findings.append("jiaan1030_service_forms 在正式庫不存在：與先前紀錄（已入庫 BA22/表單範本）不符，"
                             "需要先確認連線是否正確指向 ltc_clean，而非誤判。")

        # ── jiaan1030_ba_services 現況 ─────────────────────────────────
        ba_exists = _exists(conn, "jiaan1030_ba_services")
        print(f"JIAAN1030_BA_SERVICES_EXISTS={ba_exists}")
        if ba_exists:
            cols = _cols(conn, "jiaan1030_ba_services")
            print("JIAAN1030_BA_SERVICES_COLUMNS=" + ",".join(c["column_name"] for c in cols))
            count = conn.execute(text("SELECT COUNT(*) FROM jiaan1030_ba_services")).scalar()
            print(f"JIAAN1030_BA_SERVICES_ROW_COUNT={count}")

        # ── 0004 新表是否已存在（理論上不該存在；若存在代表本 migration 已被跑過或衝突）──
        drafts_exists = _exists(conn, "jiaan1030_service_form_drafts")
        print(f"JIAAN1030_SERVICE_FORM_DRAFTS_EXISTS={drafts_exists}")
        if drafts_exists:
            findings.append("jiaan1030_service_form_drafts 已存在於正式庫："
                             "migration 0004 若重新執行會因資料表已存在而失敗，需先確認是誰、何時建立的。")

        # ── cases 表語意確認（只看結構與型別，不讀內容）──────────────────
        case_cols = {c["column_name"] for c in _cols(conn, "cases")}
        print("CASES_TABLE_COLUMNS=" + ",".join(sorted(case_cols)))
        if {"source", "qa_item_id", "assignee_id", "reason", "summary_masked"} <= case_cols:
            print("CASES_SEMANTIC_CHECK=matches_supervisor_escalation_ticket_shape")
        else:
            findings.append("cases 表欄位與程式碼中 Case model（督導待確認案件）預期不符，需重新核對。")

        conn.rollback()

    print("\n=== FINDINGS ===")
    if not findings:
        print("（無相容性風險項目）")
    for f in findings:
        print("- " + f)
    print("\nPASS: READONLY_INSPECTION_COMPLETE_NO_WRITES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
