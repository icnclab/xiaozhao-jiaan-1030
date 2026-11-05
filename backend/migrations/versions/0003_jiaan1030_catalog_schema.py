"""Align existing jiaan1030 catalog tables with version control; add schema_status flag.

這兩張表（jiaan1030_service_forms、jiaan1030_ba_services）目前由手動 SQL 建立於正式環境，
本 migration 只補版控對齊，不覆寫既有資料；downgrade 刻意不可逆，避免誤刪正式資料。
"""
from alembic import op

revision = '0003_jiaan1030_catalog_schema'
down_revision = '0002_quality_feedback'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS jiaan1030_service_forms (
            code VARCHAR(20) PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            fields_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            reviewed BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS jiaan1030_ba_services (
            slot INTEGER PRIMARY KEY,
            code VARCHAR(20) NOT NULL,
            name VARCHAR(200) NOT NULL,
            reviewed BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    op.execute("""
        ALTER TABLE jiaan1030_service_forms
            ADD COLUMN IF NOT EXISTS schema_status VARCHAR(30) NOT NULL DEFAULT 'draft_unverified'
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_jiaan1030_service_forms_schema_status'
            ) THEN
                ALTER TABLE jiaan1030_service_forms
                    ADD CONSTRAINT ck_jiaan1030_service_forms_schema_status
                    CHECK (schema_status IN ('draft_unverified', 'verified_pending_approval', 'approved'));
            END IF;
        END $$;
    """)


def downgrade():
    raise NotImplementedError(
        "此 migration 僅補齊既有 jiaan1030_service_forms/jiaan1030_ba_services 的版控，"
        "正式環境資料並非由此 migration 建立；downgrade 需人工評估是否安全，"
        "禁止自動 DROP TABLE 以免刪除正式資料。"
    )
