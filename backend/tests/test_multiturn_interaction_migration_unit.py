"""Static ORM/migration consistency checks; no database connection."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.interaction_models import HistoryGrant, Interaction


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "0010_service_interactions.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("migration_0010", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_interaction_orm_columns_match_migration_source():
    source = MIGRATION.read_text(encoding="utf-8")
    for model in (Interaction, HistoryGrant):
        assert model.__tablename__ in source
        for column in model.__table__.columns:
            assert f'"{column.name}"' in source


def test_migration_is_linear_after_current_active_head():
    migration = _migration_module()
    assert migration.revision == "0010_service_interactions"
    assert migration.down_revision == "0009_fieldtest_participants"


def test_qa_conversation_remains_legacy_compatible_without_foreign_key():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "qa_items.conversation_id" in source
    assert 'ForeignKeyConstraint(["conversation_id"]' not in source
