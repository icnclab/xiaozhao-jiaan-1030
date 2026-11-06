"""Pure control-flow test for migrations/versions/0007_embedding_gemma_768.py's
re-run guard. No database connection -- the alembic `op` module (which only
works inside a live migration context) is replaced with a MagicMock, so this
only verifies which SQL statements upgrade()/downgrade() *decide* to run,
never actually running any of them.

Why this matters: ltc_demo's alembic_version already reads
"0007_embedding_gemma_768" and chunks.embedding is already vector(768)
(confirmed read-only in an earlier round). Alembic's own version table
normally prevents re-applying an already-applied revision, but if anyone
ever runs this file's SQL by another path (copy-pasted by hand, or after an
out-of-band alembic_version edit), the un-guarded version would silently
NULL out already-correct 768-dim vectors again -- a repeat of the exact
"retrieval stops working" incident this migration was written to cause
exactly once, on purpose, under supervision.
"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0007_embedding_gemma_768.py"
)


def _load_migration_with_mock_op():
    spec = importlib.util.spec_from_file_location("migration_0007_under_test", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    mock_op = MagicMock()
    module.op = mock_op
    return module, mock_op


def _destructive_calls(mock_op) -> list[str]:
    return [str(call.args[0]) for call in mock_op.execute.call_args_list]


def test_upgrade_skips_destructive_steps_when_already_vector_768():
    module, mock_op = _load_migration_with_mock_op()
    mock_op.get_bind.return_value.execute.return_value.scalar_one_or_none.return_value = "vector(768)"
    module.upgrade()
    assert mock_op.execute.call_count == 0, "已是 vector(768) 時不應再清空或改型別"


def test_upgrade_runs_full_sequence_when_still_vector_1024():
    module, mock_op = _load_migration_with_mock_op()
    mock_op.get_bind.return_value.execute.return_value.scalar_one_or_none.return_value = "vector(1024)"
    module.upgrade()
    calls = _destructive_calls(mock_op)
    assert any("UPDATE chunks SET embedding = NULL" in c for c in calls)
    assert any("DROP INDEX IF EXISTS ix_chunks_embedding" in c for c in calls)
    assert any("vector(768)" in c for c in calls)
    assert any("CREATE INDEX ix_chunks_embedding" in c for c in calls)


def test_upgrade_refuses_and_raises_when_column_is_missing_or_table_absent():
    # chunks.embedding not found (table/column missing) is ANOMALOUS at this
    # point in the chain -- 0001-0006 must already have created it. Treating
    # "can't tell" as "needs migration" would let a destructive UPDATE run
    # against an unexpected schema; it must raise instead, never proceed.
    module, mock_op = _load_migration_with_mock_op()
    mock_op.get_bind.return_value.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(RuntimeError, match="狀態無法判定"):
        module.upgrade()
    assert mock_op.execute.call_count == 0


def test_upgrade_refuses_and_raises_on_an_unexpected_column_type():
    # e.g. someone manually altered the column to something else entirely.
    module, mock_op = _load_migration_with_mock_op()
    mock_op.get_bind.return_value.execute.return_value.scalar_one_or_none.return_value = "text"
    with pytest.raises(RuntimeError, match="狀態無法判定"):
        module.upgrade()
    assert mock_op.execute.call_count == 0


def test_downgrade_skips_destructive_steps_when_already_vector_1024():
    module, mock_op = _load_migration_with_mock_op()
    mock_op.get_bind.return_value.execute.return_value.scalar_one_or_none.return_value = "vector(1024)"
    module.downgrade()
    assert mock_op.execute.call_count == 0


def test_downgrade_runs_full_sequence_when_still_vector_768():
    module, mock_op = _load_migration_with_mock_op()
    mock_op.get_bind.return_value.execute.return_value.scalar_one_or_none.return_value = "vector(768)"
    module.downgrade()
    calls = _destructive_calls(mock_op)
    assert any("vector(1024)" in c for c in calls)
    assert mock_op.execute.call_count == 4


def test_downgrade_refuses_and_raises_when_state_cannot_be_determined():
    module, mock_op = _load_migration_with_mock_op()
    mock_op.get_bind.return_value.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(RuntimeError, match="狀態無法判定"):
        module.downgrade()
    assert mock_op.execute.call_count == 0
