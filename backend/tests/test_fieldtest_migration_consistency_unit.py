"""Pure static consistency check between fieldtest_routes.py's SQL and the
0009 migration draft's CREATE TABLE columns. No database connection; just
text parsing. The draft is not a real .py module (kept as .draft so Alembic
never auto-loads it), so it is read as plain text, not imported.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES_SQL = (ROOT / "app" / "api" / "fieldtest_routes.py").read_text(encoding="utf-8")
DRAFT_SQL = (ROOT / "migrations" / "versions" / "0009_fieldtest_participants.py.draft").read_text(encoding="utf-8")

EXPECTED_COLUMNS = {"org_id", "code", "user_id", "assigned_by", "assigned_at"}


def _draft_columns() -> set[str]:
    create = re.search(r"CREATE TABLE IF NOT EXISTS fieldtest_participants \((.*?)\)\s*\"\"\"",
                        DRAFT_SQL, re.DOTALL)
    assert create, "draft 找不到 fieldtest_participants 的 CREATE TABLE 區塊"
    cols = set()
    for line in create.group(1).splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith("PRIMARY KEY"):
            continue
        cols.add(line.split()[0])
    return cols


def test_draft_declares_exactly_the_columns_the_routes_reference():
    referenced = set(re.findall(r"\b(org_id|code|user_id|assigned_by|assigned_at)\b",
                                 ROUTES_SQL))
    assert referenced <= EXPECTED_COLUMNS
    assert _draft_columns() == EXPECTED_COLUMNS


def test_draft_has_conflict_target_matching_on_conflict_clause():
    on_conflict = re.search(r"ON CONFLICT \(([^)]+)\)", ROUTES_SQL)
    assert on_conflict, "routes.py 應該有 ON CONFLICT 子句"
    target_cols = {c.strip() for c in on_conflict.group(1).split(",")}
    primary_key = re.search(r"PRIMARY KEY \(([^)]+)\)", DRAFT_SQL)
    assert primary_key, "draft 應該宣告對應 ON CONFLICT 目標的 PRIMARY KEY"
    draft_pk_cols = {c.strip() for c in primary_key.group(1).split(",")}
    assert draft_pk_cols == target_cols


def test_draft_chains_directly_after_0007_independent_of_webpush_draft():
    # Chain reordered this round: 0006 -> 0007 -> 0009 (fieldtest) -> 0008
    # (webpush), so fieldtest can be activated without first activating
    # Web Push. Still a single linear chain, just fieldtest and webpush
    # swapped order relative to an earlier round.
    assert 'down_revision = "0007_embedding_gemma_768"' in DRAFT_SQL


def test_draft_upgrade_has_no_destructive_statement():
    upgrade_body = DRAFT_SQL.split("def upgrade()")[1].split("def downgrade()")[0]
    for forbidden in ("DROP TABLE", "DELETE FROM", "TRUNCATE", "ALTER TABLE"):
        assert forbidden not in upgrade_body.upper()
    assert "IF NOT EXISTS" in upgrade_body
