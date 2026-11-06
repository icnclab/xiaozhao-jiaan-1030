"""Backs app/api/fieldtest_routes.py's `fieldtest_participants` mapping table
(47-person field-test code <-> user_id mapping). No existing migration or
schema file defines this table anywhere in the repository -- this is a
genuine gap, not a deliberate policy exclusion like 0007/Web Push.

Fully additive (CREATE TABLE IF NOT EXISTS), no ALTER of any existing table,
no data deletion. Chain position: rebased directly onto 0007 (not onto 0008)
so field-test can be activated without first activating Web Push --
field-test has no DB-content dependency on Web Push, only a prior-round
chain-ordering coupling. 0008 (Web Push, still kept as .draft, not activated
by this change) chains after this revision instead (0007 -> 0009 -> 0008),
keeping a single linear chain with no new Alembic heads.

Activated (renamed from .draft to .py) only after end-to-end verification in
a brand-new, fully isolated Docker Postgres instance (fresh container/
volume/port/credentials, never touching ltc_clean/ltc_demo/ltc_test): 0001-
0007 applied cleanly, then this revision alone applied directly on top of
0007 with 0008 never loaded (its tables provably absent), the full
47-participant mapping/role-check/summary/Excel-export flow passed against
the real FastAPI app, and 0009 -> 0008 still upgraded cleanly afterward with
a single alembic_version row and this table's data untouched. NOT yet
applied to any real (dev/demo/production) database -- activation here is
a code/version-control change only.

CREATE TABLE IF NOT EXISTS safety gap: if a table named fieldtest_participants
already exists with some other, incomplete structure (nothing currently
suggests this has happened, unlike 0008's Web Push tables, but there is no
way to rule it out without a database connection), IF NOT EXISTS would
silently skip creation and leave it in place while Alembic still marks this
revision as applied. upgrade() now re-reads the table's actual columns and
primary key after the CREATE statement and raises immediately if they don't
match what app/api/fieldtest_routes.py requires. It never DROPs, ALTERs, or
overwrites anything itself.
"""
from alembic import op
import sqlalchemy as sa

REQUIRED_COLUMNS = {"org_id", "code", "user_id", "assigned_by", "assigned_at"}
REQUIRED_PRIMARY_KEY = {"org_id", "code"}


def _columns(conn) -> set[str]:
    return {row[0] for row in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
    ), {"t": "fieldtest_participants"})}


def _primary_key_columns(conn) -> set[str]:
    rows = conn.execute(sa.text(
        "SELECT ccu.column_name "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema "
        "WHERE tc.table_name = :t AND tc.constraint_type = 'PRIMARY KEY'"
    ), {"t": "fieldtest_participants"}).scalars().all()
    return set(rows)


revision = "0009_fieldtest_participants"
down_revision = "0007_embedding_gemma_768"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS fieldtest_participants (
            org_id uuid NOT NULL REFERENCES organizations(id),
            code varchar(10) NOT NULL,
            user_id uuid NOT NULL REFERENCES users(id),
            assigned_by uuid NOT NULL REFERENCES users(id),
            assigned_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (org_id, code)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_fieldtest_participants_user
            ON fieldtest_participants(user_id)
    """)

    conn = op.get_bind()
    existing = _columns(conn)
    if not existing:
        raise RuntimeError("fieldtest_participants 建立後仍查無任何欄位，資料庫狀態異常，拒絕繼續，請人工檢查")
    missing = REQUIRED_COLUMNS - existing
    if missing:
        raise RuntimeError(
            f"fieldtest_participants 已存在但缺少欄位：{sorted(missing)}；"
            "可能是不完整的舊版結構被 CREATE TABLE IF NOT EXISTS 略過建立。"
            "本程式拒絕自動 DROP／ALTER／覆寫既有資料；"
            "請人工確認目前實際結構，視需要備份後手動補齊欄位，再重新套用此 Migration。"
        )
    if _primary_key_columns(conn) != REQUIRED_PRIMARY_KEY:
        raise RuntimeError(
            "fieldtest_participants 的主鍵不是 (org_id, code)；可能是舊版結構遺留。"
            "本程式拒絕自動修改主鍵，請人工確認後處理。"
        )


def downgrade() -> None:
    op.drop_table("fieldtest_participants")
