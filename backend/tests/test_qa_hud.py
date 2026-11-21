"""AR眼鏡HUD精簡回應（format=hud）：answered／escalated 兩種情境，且不影響原 /qa/ask 完整結構。"""

from __future__ import annotations

from tests.conftest import login_liff, new_id


def ask(client, headers, question, format_: str | None = None, **extra):
    body = {"question": question, "client_request_id": new_id(), **extra}
    path = "/api/qa/ask" if not format_ else f"/api/qa/ask?format={format_}"
    response = client.post(path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_hud_answered_has_summary_and_top_citation(client, world):
    headers = login_liff(client, "cg1")
    data = ask(client, headers, "夜間每多少位住民要配置一名照服員？", format_="hud")
    assert data["outcome"] == "answered", data
    assert data["escalation_reason_text"] is None
    assert data["hud_summary"], data
    assert len(data["hud_summary"]) <= 61  # 60 字 + 可能的「…」
    assert data["top_citation"]
    assert data["top_citation"]["document_title"]
    assert data["top_citation"]["locator"]
    # HUD 回應刻意精簡：不應帶完整版的重欄位
    assert set(data.keys()) == {"outcome", "escalation_reason_text", "hud_summary", "top_citation"}


def test_hud_escalated_has_reason_and_no_citation(client, world):
    headers = login_liff(client, "cg1")
    data = ask(client, headers, "員工停車位怎麼申請？", format_="hud")
    assert data["outcome"] == "escalated", data
    assert data["escalation_reason_text"]
    assert data["hud_summary"] is None
    assert data["top_citation"] is None


def test_default_qa_ask_unaffected_by_hud_feature(client, world):
    """沒帶 format 參數時，回應結構必須跟原本完全一樣（含 citations 陣列、claims 等舊欄位）。"""
    headers = login_liff(client, "cg1")
    data = ask(client, headers, "夜間每多少位住民要配置一名照服員？")
    assert data["outcome"] == "answered"
    assert "citations" in data and data["citations"]
    assert "claims" in data
    assert "case" in data
    assert "modes" in data
    assert "hud_summary" not in data
    assert "top_citation" not in data


def test_explicit_format_full_matches_default(client, world):
    headers = login_liff(client, "cg1")
    default = ask(client, headers, "員工停車位怎麼申請？")
    full = ask(client, headers, "照護紀錄要保存多久？")
    # 兩次呼叫是不同問題（避免 idempotent 命中同一筆），只驗證「省略 format」本身不會變成 HUD 結構。
    for data in (default, full):
        assert "hud_summary" not in data and "top_citation" not in data
