"""Pure control-flow tests for the post-CREATE-TABLE structural verification
added to the 0008 (Web Push) and 0009 (field-test) migration drafts this
round. No database connection -- `alembic.op` is replaced with a MagicMock
before loading each draft module, so none of their SQL ever actually runs;
`conn.execute(...)` is faked per-query by inspecting the SQL text.

Why this matters: `CREATE TABLE IF NOT EXISTS` silently does nothing if a
table with that name already exists -- including an incomplete, leftover
version from an earlier, buggy attempt (jiaan_webpush.py's own comment
references "the successful one-device test", which this session could
not confirm or rule out ran the pre-fix deploy/fieldtest/
jiaan_webpush_schema.sql against some real database). Without a check
*after* the CREATE statement, Alembic would still mark the revision as
"applied" while the actual table stays broken. Both drafts now re-read the
actual columns/constraints and raise instead of silently succeeding.
"""
import importlib.machinery
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _load_draft_with_mock_op(filename: str):
    # The file is named *.py.draft so Alembic's directory scan never loads
    # it; importlib doesn't recognize that extension by default, so the
    # source loader is passed explicitly.
    path = VERSIONS_DIR / filename
    name = f"draft_under_test_{filename}"
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    mock_op = MagicMock()
    module.op = mock_op
    return module, mock_op


def _rows_query(execute_mock, columns_by_table: dict[str, list[str]],
                 unique_by_table: dict[str, list[list[str]]] | None = None,
                 primary_key_by_table: dict[str, list[str]] | None = None):
    unique_by_table = unique_by_table or {}
    primary_key_by_table = primary_key_by_table or {}

    def side_effect(stmt, params=None):
        sql = str(stmt)
        table = (params or {}).get("t")
        result = MagicMock()
        if "information_schema.columns" in sql:
            cols = columns_by_table.get(table, [])
            result.__iter__.return_value = iter([(c,) for c in cols])
        elif "constraint_type = :ct" in sql or "constraint_type = 'PRIMARY KEY'" in sql:
            ctype = (params or {}).get("ct", "PRIMARY KEY")
            if ctype == "UNIQUE":
                groups = unique_by_table.get(table, [])
                rows = [(f"uq_{i}", col) for i, group in enumerate(groups) for col in group]
            else:
                rows = [(col,) for col in primary_key_by_table.get(table, [])]
            result.all.return_value = rows
            result.scalars.return_value.all.return_value = [r[0] for r in rows]
        else:
            raise AssertionError(f"Unexpected query in test: {sql}")
        return result

    execute_mock.side_effect = side_effect


SUB_COLS = ["id", "user_id", "org_id", "endpoint", "endpoint_hash", "p256dh", "auth",
            "is_active", "created_at", "updated_at"]
DEL_COLS = ["id", "emergency_id", "subscription_id", "stage", "status", "attempts",
            "created_at", "attempted_at"]


def test_0008_passes_when_tables_have_the_complete_committed_structure():
    module, mock_op = _load_draft_with_mock_op("0008_jiaan_webpush_proposal.py.draft")
    conn = mock_op.get_bind.return_value
    _rows_query(
        conn.execute,
        columns_by_table={"jiaan_webpush_subscriptions": SUB_COLS, "jiaan_webpush_deliveries": DEL_COLS},
        unique_by_table={
            "jiaan_webpush_subscriptions": [["endpoint_hash"]],
            "jiaan_webpush_deliveries": [["emergency_id", "subscription_id", "stage"]],
        },
    )
    module.upgrade()  # must not raise


def test_0008_raises_when_a_preexisting_subscriptions_table_lacks_endpoint_hash():
    # Simulates the suspected scenario: the old, buggy schema already ran
    # by hand, so CREATE TABLE IF NOT EXISTS left it untouched.
    module, mock_op = _load_draft_with_mock_op("0008_jiaan_webpush_proposal.py.draft")
    conn = mock_op.get_bind.return_value
    broken_cols = [c for c in SUB_COLS if c != "endpoint_hash"]
    _rows_query(
        conn.execute,
        columns_by_table={"jiaan_webpush_subscriptions": broken_cols, "jiaan_webpush_deliveries": DEL_COLS},
        unique_by_table={"jiaan_webpush_deliveries": [["emergency_id", "subscription_id", "stage"]]},
    )
    with pytest.raises(RuntimeError, match="endpoint_hash"):
        module.upgrade()


def test_0008_raises_when_endpoint_hash_column_exists_but_has_no_unique_constraint():
    module, mock_op = _load_draft_with_mock_op("0008_jiaan_webpush_proposal.py.draft")
    conn = mock_op.get_bind.return_value
    _rows_query(
        conn.execute,
        columns_by_table={"jiaan_webpush_subscriptions": SUB_COLS, "jiaan_webpush_deliveries": DEL_COLS},
        unique_by_table={},  # no UNIQUE constraints found anywhere
    )
    with pytest.raises(RuntimeError, match="UNIQUE"):
        module.upgrade()


def test_0009_passes_when_table_has_the_complete_structure():
    module, mock_op = _load_draft_with_mock_op("0009_fieldtest_participants.py.draft")
    conn = mock_op.get_bind.return_value
    _rows_query(
        conn.execute,
        columns_by_table={"fieldtest_participants": ["org_id", "code", "user_id", "assigned_by", "assigned_at"]},
        primary_key_by_table={"fieldtest_participants": ["org_id", "code"]},
    )
    module.upgrade()  # must not raise


def test_0009_raises_when_a_preexisting_table_is_missing_a_required_column():
    module, mock_op = _load_draft_with_mock_op("0009_fieldtest_participants.py.draft")
    conn = mock_op.get_bind.return_value
    _rows_query(
        conn.execute,
        columns_by_table={"fieldtest_participants": ["org_id", "code", "user_id"]},  # missing assigned_by/assigned_at
    )
    with pytest.raises(RuntimeError, match="缺少欄位"):
        module.upgrade()


def test_0009_raises_when_primary_key_does_not_match():
    module, mock_op = _load_draft_with_mock_op("0009_fieldtest_participants.py.draft")
    conn = mock_op.get_bind.return_value
    _rows_query(
        conn.execute,
        columns_by_table={"fieldtest_participants": ["org_id", "code", "user_id", "assigned_by", "assigned_at"]},
        primary_key_by_table={"fieldtest_participants": ["code"]},  # wrong PK
    )
    with pytest.raises(RuntimeError, match="主鍵"):
        module.upgrade()
