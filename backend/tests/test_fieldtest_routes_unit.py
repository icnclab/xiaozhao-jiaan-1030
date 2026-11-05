"""Pure-logic unit tests for fieldtest_routes._admin(); no database connection."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.fieldtest_routes import CODES, MappingInput, _admin


def _user(role="admin", org_id="org-1"):
    return SimpleNamespace(role=role, org_id=org_id)


def test_admin_allows_admin_with_org():
    assert _admin(_user()) == "org-1"


@pytest.mark.parametrize("role", ["caregiver", "supervisor", "director", "", None])
def test_admin_rejects_non_admin_roles(role):
    with pytest.raises(HTTPException) as exc:
        _admin(_user(role=role))
    assert exc.value.status_code == 403


def test_admin_rejects_missing_org_id():
    with pytest.raises(HTTPException) as exc:
        _admin(_user(role="admin", org_id=None))
    assert exc.value.status_code == 403


def test_admin_accepts_enum_like_role_value():
    # Some role representations are enum-like objects exposing .value.
    role = SimpleNamespace(value="admin")
    assert _admin(_user(role=role)) == "org-1"


def test_codes_cover_40_caregivers_and_7_supervisors():
    assert len(CODES) == 47
    assert CODES[0] == "A01" and CODES[39] == "A40"
    assert CODES[40] == "S01" and CODES[-1] == "S07"


def test_mapping_input_requires_code_and_user_id():
    body = MappingInput(code="a01", user_id="11111111-1111-1111-1111-111111111111")
    assert body.code == "a01"  # route-level code normalizes to upper() itself
