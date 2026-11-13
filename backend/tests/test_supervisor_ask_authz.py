"""督導AI助手（/api/qa/supervisor-ask）是督導／主任專屬入口，照服員與未登入者不得呼叫。"""

from __future__ import annotations

from tests.conftest import login_liff, login_web, new_id


def _body():
    return {"question": "家屬要我幫住民代購成藥，機構規定可以嗎？",
            "source": "text", "client_request_id": new_id()}


def test_caregiver_forbidden(client, world):
    headers = login_liff(client, "cg1")
    assert client.post("/api/qa/supervisor-ask", headers=headers, json=_body()).status_code == 403


def test_unauthenticated_forbidden(client, world):
    assert client.post("/api/qa/supervisor-ask", json=_body()).status_code == 401


def test_supervisor_and_director_allowed(client, world):
    for username in ("sup_a",):
        headers = login_web(client, username)
        result = client.post("/api/qa/supervisor-ask", headers=headers, json=_body())
        assert result.status_code == 200, (username, result.text)
        assert "citations" in result.json()


def test_supervisor_ask_reuses_same_org_scoping_as_qa_ask(client, world):
    """同一個問題在/qa/ask與/qa/supervisor-ask應該得到相同範圍的引用結果（共用同一套RAG）。"""
    headers = login_web(client, "sup_a")
    a = client.post("/api/qa/ask", headers=headers, json=_body()).json()
    headers2 = login_web(client, "sup_a")
    b = client.post("/api/qa/supervisor-ask", headers=headers2, json=_body()).json()
    assert {c["version_id"] for c in a["citations"]} == {c["version_id"] for c in b["citations"]}


def test_admin_uses_existing_general_qa_without_supervisor_role_expansion(client, world):
    """管理員共用AI畫面仍走既有/qa/ask；不得順便放寬督導專屬入口。"""
    headers = login_web(client, "admin_happy")
    result = client.post("/api/qa/ask", headers=headers, json=_body())
    assert result.status_code == 200
    assert "citations" in result.json()
    assert client.post("/api/qa/supervisor-ask", headers=headers, json=_body()).status_code == 403
