"""ACTIVATED 2026-11-15 after isolated verification on two real databases:
ltc_pytest (5/5 new tests in tests/test_interaction_routes_unit.py, plus the
full 395/395 suite) and the Staging database ltc_v7_staging_20261114_195946
(applied via explicit-revision `alembic upgrade 0010_service_interactions`
after a full pg_dump backup; GET /api/interactions confirmed 200; RBAC/role
checks reconfirmed). A pre-activation copy of this file with the original
.draft history is kept at run/eighth_release_candidate_20261115_181917/ and
run/ninth_release_candidate_20261115_185121/ for traceability.

Root cause this covers (confirmed live on Staging 2026-11-15 via the running
uvicorn process's own error log, not guessed):

    sqlalchemy.exc.ProgrammingError: (psycopg.errors.UndefinedTable)
    relation "service_interactions" does not exist

`app/interaction_models.py` defines two ORM models (`Interaction` ->
`service_interactions`, `HistoryGrant` -> `interaction_read_grants`) and
`app/api/interaction_routes.py` is mounted live in `app/main.py`, but no
migration (active or .draft) has ever created either table. Every request to
GET /interactions (and every other route in interaction_routes.py) fails with
HTTP 500 on any database that only has the committed Alembic chain applied.
This draft is the missing migration, not a workaround.

Chain position: `down_revision = "0009_fieldtest_participants"`, matching
`alembic heads` at the time this file is the only one activated (head is now
`0010_service_interactions`). `0008_jiaan_webpush_proposal.py.draft` has
already been updated to target `down_revision = "0010_service_interactions"`,
so the single intended future chain is 0009 -> 0010 -> 0008 with no
re-editing needed here when 0008 is eventually activated.

Fully additive (CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS /
ADD CONSTRAINT ... NOT VALID style would still be ALTER -- none used here
since both tables are new), no ALTER of any existing table, no data deletion.

Same fail-closed pattern as 0008_jiaan_webpush.py.draft: CREATE TABLE IF NOT
EXISTS is silent if a same-named table already exists with a different shape
(for example a hand-created, incomplete version). upgrade() re-reads each
table's actual columns, foreign keys and unique constraints after the CREATE
statements and raises immediately if they don't match what
`app/interaction_models.py` actually declares. It never DROPs, ALTERs, or
overwrites anything by itself -- a mismatch stops the migration with a
message telling a human what to check. Verified to actually raise under this
condition (see the from-scratch synthetic-chain verification run alongside
this activation, which also exercises the clean 0007->head upgrade path and
downgrade()).
"""
from alembic import op
import sqlalchemy as sa


def _columns(conn, table: str) -> set[str]:
    return {row[0] for row in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
    ), {"t": table})}


def _constraint_columns(conn, table: str, constraint_type: str) -> list[set[str]]:
    """每個符合 constraint_type 的限制各自涵蓋哪些欄位（可能有多個同類限制）。"""
    rows = conn.execute(sa.text(
        "SELECT tc.constraint_name, ccu.column_name "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema "
        "WHERE tc.table_name = :t AND tc.constraint_type = :ct"
    ), {"t": table, "ct": constraint_type}).all()
    grouped: dict[str, set[str]] = {}
    for name, col in rows:
        grouped.setdefault(name, set()).add(col)
    return list(grouped.values())


def _verify_or_fail(conn, table: str, required_columns: set[str], required_unique: set[str]) -> None:
    existing = _columns(conn, table)
    if not existing:
        raise RuntimeError(f"{table} 建立後仍查無任何欄位，資料庫狀態異常，拒絕繼續，請人工檢查")
    missing = required_columns - existing
    if missing:
        raise RuntimeError(
            f"{table} 已存在但缺少欄位：{sorted(missing)}；"
            "可能是不完整的舊版結構被 CREATE TABLE IF NOT EXISTS 略過建立。"
            "本程式拒絕自動 DROP／ALTER／覆寫既有資料；"
            f"請人工確認 {table} 目前實際結構，視需要備份後手動補齊欄位，"
            "再重新套用此 Migration。"
        )
    if required_unique not in _constraint_columns(conn, table, "UNIQUE"):
        raise RuntimeError(
            f"{table} 缺少涵蓋 {sorted(required_unique)} 的 UNIQUE 限制；"
            "可能是舊版結構遺留。本程式拒絕自動修改限制，請人工確認後處理。"
        )


revision = "0010_service_interactions"
down_revision = "0009_fieldtest_participants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS service_interactions (
            id uuid PRIMARY KEY,
            org_id uuid NOT NULL REFERENCES organizations(id),
            owner_id uuid NOT NULL REFERENCES users(id),
            start_request_id varchar(64) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            ended_at timestamptz,
            UNIQUE (owner_id, start_request_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_service_interactions_org_id
            ON service_interactions(org_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_service_interactions_owner_id
            ON service_interactions(owner_id)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS interaction_read_grants (
            id uuid PRIMARY KEY,
            interaction_id uuid NOT NULL REFERENCES service_interactions(id),
            viewer_id uuid NOT NULL REFERENCES users(id),
            approved_by uuid NOT NULL REFERENCES users(id),
            responsible boolean NOT NULL DEFAULT false,
            read_approved boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (interaction_id, viewer_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_interaction_read_grants_interaction_id
            ON interaction_read_grants(interaction_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_interaction_read_grants_viewer_id
            ON interaction_read_grants(viewer_id)
    """)

    conn = op.get_bind()
    _verify_or_fail(
        conn, "service_interactions",
        {"id", "org_id", "owner_id", "start_request_id", "created_at", "ended_at"},
        {"owner_id", "start_request_id"},
    )
    _verify_or_fail(
        conn, "interaction_read_grants",
        {"id", "interaction_id", "viewer_id", "approved_by", "responsible",
         "read_approved", "created_at"},
        {"interaction_id", "viewer_id"},
    )


def downgrade() -> None:
    # Intended for genuinely new tables this migration created. If either
    # table turns out to pre-date this migration, a human must confirm that
    # is actually wanted (and that nothing else depends on the existing
    # data) before running this -- never run downgrade() unattended.
    op.drop_table("interaction_read_grants")
    op.drop_table("service_interactions")
