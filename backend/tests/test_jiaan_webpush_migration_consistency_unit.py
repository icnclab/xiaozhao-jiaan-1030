"""Pure static consistency checks between the already-committed Web Push
application code (app/services/jiaan_webpush.py, app/api/jiaan_webpush_routes.py
-- commit 0a3d16a) and the still-draft migration that is supposed to create
the tables it depends on. No database connection; text parsing only.

This exists because a fresh git clone today already registers
jiaan_webpush_routes in main.py (committed) but no committed migration
creates jiaan_webpush_subscriptions/jiaan_webpush_deliveries -- the draft is
the missing dependency, and it must declare exactly the columns/constraints
the committed code actually uses, or activating it would fail at runtime.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "app" / "services" / "jiaan_webpush.py").read_text(encoding="utf-8")
ROUTES = (ROOT / "app" / "api" / "jiaan_webpush_routes.py").read_text(encoding="utf-8")
DRAFT = (ROOT / "migrations" / "versions" / "0008_jiaan_webpush_proposal.py.draft").read_text(encoding="utf-8")
CODE = SERVICE + "\n" + ROUTES


def _create_table_block(table: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\)\s*\"\"\"", DRAFT, re.DOTALL
    )
    assert match, f"draft 找不到 {table} 的 CREATE TABLE 區塊"
    return match.group(1)


def _declared_columns(table: str) -> set[str]:
    cols = set()
    for line in _create_table_block(table).splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY KEY", "UNIQUE", "CHECK")):
            continue
        cols.add(line.split()[0])
    return cols


def test_subscriptions_table_declares_endpoint_hash_column_the_code_requires():
    # subscribe()/unsubscribe() both insert/filter on endpoint_hash; a draft
    # without this column would make every subscribe() call fail at runtime.
    assert "endpoint_hash" in CODE
    assert "endpoint_hash" in _declared_columns("jiaan_webpush_subscriptions")


def test_subscriptions_table_unique_constraint_targets_endpoint_hash_not_endpoint():
    # ON CONFLICT (endpoint_hash) requires a matching UNIQUE constraint on
    # endpoint_hash; endpoint itself is stored Fernet-encrypted (non
    # -deterministic per call), so UNIQUE on endpoint would be meaningless.
    on_conflict = re.search(r"ON CONFLICT \(([^)]+)\)", ROUTES)
    assert on_conflict and on_conflict.group(1).strip() == "endpoint_hash"
    block = _create_table_block("jiaan_webpush_subscriptions")
    assert re.search(r"endpoint_hash text NOT NULL UNIQUE", block)
    assert not re.search(r"\bendpoint text NOT NULL UNIQUE\b", block)


def test_subscriptions_table_declares_every_column_the_code_reads_or_writes():
    referenced = set(re.findall(
        r"\b(id|user_id|org_id|endpoint|endpoint_hash|p256dh|auth|is_active|created_at|updated_at)\b",
        CODE,
    ))
    declared = _declared_columns("jiaan_webpush_subscriptions")
    assert referenced <= declared, referenced - declared


def test_deliveries_table_declares_every_column_the_code_reads_or_writes():
    referenced = set(re.findall(
        r"\b(id|emergency_id|subscription_id|stage|status|attempts|created_at|attempted_at)\b",
        SERVICE,
    ))
    declared = _declared_columns("jiaan_webpush_deliveries")
    assert referenced <= declared, referenced - declared


def test_deliveries_table_unique_constraint_matches_sweep_on_conflict_target():
    on_conflict = re.search(r"ON CONFLICT \(([^)]+)\)", SERVICE)
    assert on_conflict
    target_cols = {c.strip() for c in on_conflict.group(1).split(",")}
    unique = re.search(r"UNIQUE \(([^)]+)\)", _create_table_block("jiaan_webpush_deliveries"))
    assert unique, "draft 應宣告對應 ON CONFLICT 目標的 UNIQUE 限制"
    draft_cols = {c.strip() for c in unique.group(1).split(",")}
    assert draft_cols == target_cols


def test_draft_chains_after_interaction_draft_not_fieldtest_directly():
    # Chain reordered again this round: 0010_service_interactions (the P0
    # fix for the missing service_interactions/interaction_read_grants
    # tables) was inserted between 0009 (fieldtest) and this file, giving
    # 0006 -> 0007 -> 0009 -> 0010 -> 0008. Still a single linear chain,
    # and 0008/0010 remain content-independent of each other.
    assert 'down_revision = "0010_service_interactions"' in DRAFT


def test_draft_upgrade_has_no_destructive_statement():
    # ALTER TABLE itself is allowed this round (the folded-in outbox
    # extension uses ADD COLUMN IF NOT EXISTS / ADD CONSTRAINT / a
    # backfilled ALTER COLUMN ... SET NOT NULL, all additive on a table
    # this same migration just created) -- only genuinely destructive
    # statement *shapes* are banned, checked independently of each other so
    # one being absent doesn't let a different one hide in the same line.
    upgrade_body = DRAFT.split("def upgrade()")[1].split("def downgrade()")[0]
    upper = upgrade_body.upper()
    for forbidden in ("DROP TABLE", "DELETE FROM", "TRUNCATE", "DROP COLUMN", "DROP CONSTRAINT"):
        assert forbidden not in upper
    # Every ALTER TABLE statement (which may span multiple lines before its
    # terminating ';') must be one of the three additive shapes.
    for stmt in re.findall(r"ALTER TABLE\b.*?;", upgrade_body, re.DOTALL | re.IGNORECASE):
        assert any(allowed in stmt.upper() for allowed in
                   ("ADD COLUMN IF NOT EXISTS", "ADD CONSTRAINT", "SET NOT NULL")), stmt


def test_pywebpush_is_a_declared_dependency_and_actually_importable():
    # jiaan_webpush.py lazy-imports pywebpush inside _send_one() only, so a
    # missing declaration would not fail at app startup -- only when a real
    # dispatch is attempted. Must be declared so a clean checkout's install
    # actually has it.
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'"pywebpush[>=<]', pyproject), "pyproject.toml 未宣告 pywebpush 相依"
    import pywebpush  # noqa: F401 -- confirms it is actually installed here
