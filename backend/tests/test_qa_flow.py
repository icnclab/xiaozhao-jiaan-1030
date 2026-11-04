"""A1／A2／A3：附出處回答、轉督導、建案失敗不顯示已轉交。"""

from __future__ import annotations

from sqlalchemy import select

from app.db import new_session
from app.models import AuditLog, Case, QaItem
from app.providers.llm import MockLlm
from app.services import cases as case_service
from tests.conftest import login_liff, new_id


def ask(client, headers, question, **extra):
    body = {"question": question, "client_request_id": new_id(), **extra}
    response = client.post("/api/qa/ask", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_answer_with_citation_version(client, world):
    """A1：現行版本（第 2 版）的條文被引用，出處入口回到同一版本。"""
    headers = login_liff(client, "cg1")
    data = ask(client, headers, "夜間每多少位住民要配置一名照服員？")
    assert data["outcome"] == "answered", data
    assert data["label"] == "AI 初步參考"
    assert data["citations"], data
    top = data["citations"][0]
    assert top["version_label"] == "第 2 版"
    assert top["version_id"] == str(world.ids["reg_v2"])
    assert "二十位" in data["answer_text"]
    # 出處入口由後端產生，回到該版本原文
    source = client.get(top["source_url"], headers=headers).json()
    assert source["version"]["id"] == str(world.ids["reg_v2"])
    assert "二十位" in source["chunk"]["text"]
    # 不顯示相似度或正確率
    assert "score" not in str(data["citations"]) and "confidence" not in data


def test_escalate_no_evidence(client, world):
    """A2：知識庫沒有依據 → 轉督導並建案。"""
    headers = login_liff(client, "cg1")
    data = ask(client, headers, "員工停車位怎麼申請？")
    assert data["outcome"] == "escalated"
    assert data["escalation_reason"] == "no_evidence"
    assert data["case"] and data["case"]["status"] == "pending"


def test_escalate_conflict(client, world):
    """A2：營運規範（24 小時）與機構 SOP（48 小時）衝突 → 轉督導。"""
    headers = login_liff(client, "cg1")
    # A rule conflict question must not assert a current safety incident.
    data = ask(client, headers, "異常事件發生後，要在幾小時內完成紀錄？")
    assert data["outcome"] == "escalated"
    assert data["escalation_reason"] == "conflict"
    assert data["case"]


def test_escalate_clinical_and_medication(client, world):
    """A2：臨床、用藥、補助金額、緊急 → 規則轉人工，不進生成。"""
    headers = login_liff(client, "cg1")
    cases = {
        "住民發燒到 38.5 度要不要送醫？": "risk_clinical",
        "安眠藥可以多給半顆嗎？要不要給藥": "risk_medication",
        "住宿式機構的補助可以領多少錢？": "risk_subsidy_amount",
        "住民突然昏倒叫不醒怎麼辦？": "risk_emergency",
    }
    for question, reason in cases.items():
        data = ask(client, headers, question)
        assert data["outcome"] == "escalated", (question, data)
        assert data["escalation_reason"] == reason, (question, data)
        assert data["citations"] == []


def test_emergency_note_is_fixed_guidance(client, world):
    """照服員遇緊急狀況，應明確提示立即撥打119/110，不等待小照或居督回覆（1030訪談角色提示語修正後的行為）。"""
    headers = login_liff(client, "cg1")
    data = ask(client, headers, "住民昏倒了沒有呼吸")
    assert data["escalation_reason"] == "risk_emergency"
    assert "119" in data["answer_text"] and "110" in data["answer_text"]
    assert "不要等待小照或居督回覆" in data["answer_text"]


def test_case_creation_failure(client, world):
    """A3：建案失敗時 outcome=escalation_failed、沒有案件，重試成功後才有案件。"""
    headers = login_liff(client, "cg1")
    case_service.FAULT_INJECTION = RuntimeError("db down")
    data = ask(client, headers, "員工停車位怎麼申請？")
    assert data["outcome"] == "escalation_failed"
    assert data["case"] is None
    assert data["case_error"]
    session = new_session()
    assert session.scalar(select(Case)) is None
    assert session.scalar(select(AuditLog).where(AuditLog.action == "case.create", AuditLog.outcome == "error"))
    session.close()
    # 故障排除後重試
    case_service.FAULT_INJECTION = None
    retried = client.post(f"/api/qa/{data['id']}/retry-escalation", headers=headers).json()
    assert retried["outcome"] == "escalated"
    assert retried["case"]["number"].startswith("C-")
    # 再按一次不會產生第二個案件
    client.post(f"/api/qa/{data['id']}/retry-escalation", headers=headers)
    session = new_session()
    assert len(session.scalars(select(Case)).all()) == 1
    session.close()


def test_manual_escalation_failure_returns_503(client, world):
    headers = login_liff(client, "cg1")
    data = ask(client, headers, "照護紀錄要保存多久？")
    assert data["outcome"] == "answered"
    case_service.FAULT_INJECTION = RuntimeError("db down")
    response = client.post(f"/api/qa/{data['id']}/escalate", json={"client_request_id": new_id()}, headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["retryable"] is True
    case_service.FAULT_INJECTION = None
    request_id = new_id()
    first = client.post(f"/api/qa/{data['id']}/escalate", json={"client_request_id": request_id}, headers=headers)
    second = client.post(f"/api/qa/{data['id']}/escalate", json={"client_request_id": request_id}, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["case"]["id"] == second.json()["case"]["id"]


def test_ask_idempotent(client, world):
    headers = login_liff(client, "cg1")
    body = {"question": "員工停車位怎麼申請？", "client_request_id": new_id()}
    first = client.post("/api/qa/ask", json=body, headers=headers).json()
    second = client.post("/api/qa/ask", json=body, headers=headers).json()
    assert first["id"] == second["id"]
    assert first["case"]["id"] == second["case"]["id"]


def test_question_is_stored_masked(client, world):
    headers = login_liff(client, "cg1")
    data = ask(client, headers, "302 王先生的女兒要我幫忙代購成藥可以嗎")
    assert "王先生" not in data["question_masked"]
    session = new_session()
    stored = session.scalar(select(QaItem.question_masked))
    assert "王先生" not in stored and "302" not in stored
    session.close()


def test_llm_failure_escalates(client, world):
    headers = login_liff(client, "cg1")
    MockLlm.script = TimeoutError("ollama timeout")
    data = ask(client, headers, "照護紀錄要保存多久？")
    assert data["outcome"] == "escalated" and data["escalation_reason"] == "llm_error"


def test_llm_needs_human_escalates(client, world):
    headers = login_liff(client, "cg1")
    MockLlm.script = {"claims": [], "needs_human": True, "conflict": False, "reason": "需要知道住民失能程度"}
    data = ask(client, headers, "協助住民從床上移位到輪椅要幾個人？")
    assert data["outcome"] == "escalated" and data["escalation_reason"] == "insufficient"
