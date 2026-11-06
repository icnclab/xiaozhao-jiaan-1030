"""Route-logic unit tests for fieldtest_routes.py using mocked SQLAlchemy
calls -- no real database connection (this round still avoids any new DB
connection; verification of 0009's actual table creation stays a static
text comparison, see test_fieldtest_migration_consistency_unit.py).

These tests exercise the real set_mapping()/export_xlsx() functions, only
faking what they read from the database, to catch logic bugs (role<->code
mismatch, duplicate-code conflict, Excel column whitelist) without ever
opening a socket.
"""
import asyncio
import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

from app.api import fieldtest_routes as ft


def _admin_user(org_id="org-1"):
    return SimpleNamespace(role="admin", org_id=org_id, id="admin-1")


def _fake_inspector(tables, columns_by_table):
    insp = MagicMock()
    insp.get_table_names.return_value = tables
    insp.get_columns.side_effect = lambda table_name: [
        {"name": c} for c in columns_by_table.get(table_name, [])
    ]
    return insp


CAREGIVER_UUID = "11111111-1111-1111-1111-111111111111"
SUPERVISOR_UUID = "22222222-2222-2222-2222-222222222222"


@patch.object(ft, "inspect")
def test_set_mapping_rejects_role_code_mismatch(mock_inspect):
    mock_inspect.return_value = _fake_inspector(
        ["users", "fieldtest_participants"], {"users": ["id", "org_id", "role"]}
    )
    db = MagicMock()
    # person exists but is a supervisor, not eligible for an A-code (caregiver) slot
    db.execute.return_value.mappings.return_value.all.return_value = [
        {"id": SUPERVISOR_UUID, "role": "supervisor"}
    ]
    body = ft.MappingInput(code="A01", user_id=SUPERVISOR_UUID)
    with pytest.raises(HTTPException) as exc:
        ft.set_mapping(body, db=db, user=_admin_user())
    assert exc.value.status_code == 422
    db.commit.assert_not_called()


@patch.object(ft, "inspect")
def test_set_mapping_rejects_invalid_code_format(mock_inspect):
    mock_inspect.return_value = _fake_inspector(["users", "fieldtest_participants"], {"users": ["id", "org_id", "role"]})
    db = MagicMock()
    body = ft.MappingInput(code="Z99", user_id=CAREGIVER_UUID)
    with pytest.raises(HTTPException) as exc:
        ft.set_mapping(body, db=db, user=_admin_user())
    assert exc.value.status_code == 422


@patch.object(ft, "inspect")
def test_set_mapping_rejects_user_already_mapped_to_different_code(mock_inspect):
    mock_inspect.return_value = _fake_inspector(["users", "fieldtest_participants"], {"users": ["id", "org_id", "role"]})
    db = MagicMock()

    def execute_side_effect(stmt, params=None):
        sql = str(stmt)
        result = MagicMock()
        if "FROM users WHERE" in sql:
            result.mappings.return_value.all.return_value = [
                {"id": CAREGIVER_UUID, "role": "caregiver"}
            ]
        elif "FROM fieldtest_participants WHERE org_id=:org AND user_id" in sql:
            result.mappings.return_value.all.return_value = [{"code": "A02"}]
        else:
            result.mappings.return_value.all.return_value = []
        return result

    db.execute.side_effect = execute_side_effect
    body = ft.MappingInput(code="A01", user_id=CAREGIVER_UUID)
    with pytest.raises(HTTPException) as exc:
        ft.set_mapping(body, db=db, user=_admin_user())
    assert exc.value.status_code == 409
    db.commit.assert_not_called()


@patch.object(ft, "inspect")
def test_set_mapping_accepts_matching_caregiver_a_code(mock_inspect):
    mock_inspect.return_value = _fake_inspector(["users", "fieldtest_participants"], {"users": ["id", "org_id", "role"]})
    db = MagicMock()

    def execute_side_effect(stmt, params=None):
        sql = str(stmt)
        result = MagicMock()
        if "FROM users WHERE" in sql:
            result.mappings.return_value.all.return_value = [
                {"id": CAREGIVER_UUID, "role": "caregiver"}
            ]
        elif "FROM fieldtest_participants WHERE org_id=:org AND user_id" in sql:
            result.mappings.return_value.all.return_value = []  # no existing conflict
        else:
            result.mappings.return_value.all.return_value = []
        return result

    db.execute.side_effect = execute_side_effect
    body = ft.MappingInput(code="A01", user_id=CAREGIVER_UUID)
    out = ft.set_mapping(body, db=db, user=_admin_user())
    assert out == {"ok": True, "code": "A01", "user_id": CAREGIVER_UUID}
    db.commit.assert_called_once()


def test_export_xlsx_columns_contain_no_free_text_or_names():
    """Bypass the DB read (_data) and feed a canned, clearly-fake fixture to
    verify the Excel writer only ever emits the whitelisted columns -- never
    question text, case summaries, or display names."""
    fake_data = {
        "note": "test",
        "total": 47,
        "mapped": 1,
        "with_records": 1,
        "participants": [
            {"code": "A01", "role": "照服員", "user_id": CAREGIVER_UUID,
             "mapping_status": "已對應", "audit_event_count": 2, "qa_count": 3,
             "case_count": 1, "status": "有紀錄"},
        ],
        "events": [{"code": "A01", "user_id": CAREGIVER_UUID, "event": "qa.ask",
                     "occurred_at": "2026-11-05", "outcome": "ok"}],
        "qa": [{"code": "A01", "user_id": CAREGIVER_UUID, "record_id": "qa-1",
                 "occurred_at": "2026-11-05", "outcome": "answered", "source": "liff"}],
        "cases": [{"code": "A01", "user_id": CAREGIVER_UUID, "record_id": "case-1",
                    "number": "C-0001", "occurred_at": "2026-11-05", "status": "pending"}],
        "errors": [],
    }
    with patch.object(ft, "_data", return_value=fake_data):
        response = ft.export_xlsx(db=MagicMock(), user=_admin_user())

    async def _collect() -> bytes:
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode())
        return b"".join(chunks)

    body = asyncio.run(_collect())
    wb = load_workbook(io.BytesIO(body))
    all_cell_text = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                if cell is not None:
                    all_cell_text.append(str(cell))
    joined = " ".join(all_cell_text)
    # Must not leak any UUID beyond the one deliberately fed into the fixture,
    # and must contain none of the forbidden free-text fields.
    for forbidden in ("question_masked", "summary_masked", "display_name", "答案", "姓名"):
        assert forbidden not in joined
    assert "A01" in joined  # whitelisted fields are present


@patch.object(ft, "inspect")
def test_participant_rows_raises_clear_503_when_table_missing(mock_inspect):
    # Before the dashboard/table exists, calling summary()/export must not
    # surface a raw, unhandled DB exception (generic HTTP 500, blank page).
    mock_inspect.return_value = _fake_inspector(["users"], {"users": ["id", "org_id", "role"]})
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        ft._participant_rows(db, "org-1")
    assert exc.value.status_code == 503
    assert "fieldtest_participants" in exc.value.detail
    assert "尚未建立" in exc.value.detail
    db.execute.assert_not_called()


@patch.object(ft, "inspect")
def test_set_mapping_raises_clear_503_when_table_missing(mock_inspect):
    mock_inspect.return_value = _fake_inspector(["users"], {"users": ["id", "org_id", "role"]})
    db = MagicMock()
    body = ft.MappingInput(code="A01", user_id=CAREGIVER_UUID)
    with pytest.raises(HTTPException) as exc:
        ft.set_mapping(body, db=db, user=_admin_user())
    assert exc.value.status_code == 503
    assert "尚未建立" in exc.value.detail
    db.execute.assert_not_called()
    db.commit.assert_not_called()


@patch.object(ft, "inspect")
def test_participant_rows_mark_unset_codes_as_pending_not_participated(mock_inspect):
    """If no mapping rows exist at all, every one of the 47 codes must show
    as "待核對", never implied as already having 47 real participants."""
    mock_inspect.return_value = _fake_inspector(
        ["users", "fieldtest_participants"], {"users": ["id", "org_id", "role"]}
    )
    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = []
    rows = ft._participant_rows(db, "org-1")
    assert len(rows) == 47
    assert all(r["mapping_status"] == "待核對" for r in rows)
    assert all(r["user_id"] is None for r in rows)
