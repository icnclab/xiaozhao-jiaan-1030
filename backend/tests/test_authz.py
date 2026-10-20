"""A10：跨機構存取與檢索被阻擋；角色權限；模擬登入在正式環境停用。"""

from __future__ import annotations

from sqlalchemy import select

from app.db import new_session
from app.models import AuditLog, Chunk
from tests.conftest import login_liff, login_web, new_id


def test_cross_org_case_and_source_access_denied(client, world):
    happy = login_liff(client, "cg1")
    pine_sup = login_web(client, "sup_pine")
    pine_cg = login_liff(client, "cg_pine")
    categories = client.get("/api/categories", headers=happy).json()
    case = client.post("/api/cases", headers=happy, json={
        "category_id": categories[0]["id"], "template_id": categories[0]["templates"][0]["id"],
        "client_request_id": new_id()}).json()
    assert client.get(f"/api/admin/cases/{case['id']}", headers=pine_sup).status_code == 404
    assert client.get(f"/api/cases/{case['id']}", headers=pine_cg).status_code == 404
    assert client.post(f"/api/admin/cases/{case['id']}/reply", headers=pine_sup,
                       json={"text": "x", "client_request_id": new_id()}).status_code == 404
    # 他機構分類不能拿來建案
    assert client.post("/api/cases", headers=pine_cg, json={
        "category_id": categories[0]["id"], "text": "x", "client_request_id": new_id()}).status_code == 404
    # 幸福園內規的切塊與原始檔，松柏居的人讀不到
    session = new_session()
    chunk = session.scalar(select(Chunk).where(Chunk.version_id == world.ids["happy_scope"]))
    session.close()
    assert client.get(f"/api/sources/chunks/{chunk.id}", headers=pine_cg).status_code == 404
    assert client.get(f"/api/sources/versions/{world.ids['happy_scope']}/file", headers=pine_cg).status_code == 404
    assert client.get(f"/api/sources/chunks/{chunk.id}", headers=happy).status_code == 200
    session = new_session()
    denied = session.scalars(select(AuditLog).where(AuditLog.action == "access_denied")).all()
    assert len(denied) >= 4
    session.close()


def test_retrieval_is_org_scoped(client, world):
    """同一題：幸福園只引幸福園內規／共用規範；松柏居只引松柏居內規／共用規範。"""
    question = "家屬要我幫住民代購成藥，機構規定可以嗎？"
    for username, own, other in (("cg1", "happy_scope", "pine_scope"), ("cg_pine", "pine_scope", "happy_scope")):
        headers = login_liff(client, username)
        data = client.post("/api/qa/ask", headers=headers,
                           json={"question": question, "client_request_id": new_id()}).json()
        cited = {c["version_id"] for c in data["citations"]}
        assert str(world.ids[other]) not in cited, (username, data)
        for entry in data.get("citations", []):
            assert "居家" not in entry["document_title"]


def test_home_care_rules_not_applied_to_residential(client, world):
    headers = login_liff(client, "cg1")
    data = client.post("/api/qa/ask", headers=headers, json={
        "question": "居家服務員到宅可以協助代購日常用品及藥品嗎？", "client_request_id": new_id()}).json()
    assert all("居家" not in c["document_title"] for c in data["citations"])


def test_caregiver_cannot_use_admin_api(client, world):
    headers = login_liff(client, "cg1")
    assert client.get("/api/admin/cases", headers=headers).status_code == 403
    assert client.get("/api/admin/metrics", headers=headers).status_code == 403


def test_caregiver_cannot_login_backoffice(client, world):
    from app.auth import set_password
    from app.models import User

    session = new_session()
    user = session.get(User, world.ids["cg2"])
    set_password(user, "caregiver-pass-1")
    session.commit()
    session.close()
    response = client.post("/api/auth/login", json={"username": "cg2", "password": "caregiver-pass-1"})
    assert response.status_code == 403


def test_supervisor_cannot_publish_shared_document(client, world):
    sup = login_web(client, "sup_a")
    docs = client.get("/api/admin/documents", headers=sup).json()
    shared = next(d for d in docs if d["scope"] == "shared")
    version_id = shared["versions"][0]["id"]
    assert client.post(f"/api/admin/versions/{version_id}/deactivate", headers=sup).status_code == 403


def test_other_users_qa_not_visible(client, world):
    cg1 = login_liff(client, "cg1")
    data = client.post("/api/qa/ask", headers=cg1, json={"question": "照護紀錄要保存多久？",
                                                         "client_request_id": new_id()}).json()
    pine = login_liff(client, "cg_pine")
    assert client.get(f"/api/qa/{data['id']}", headers=pine).status_code == 404


def test_dev_login_disabled_in_production(client, world, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "app_env", "production")
    response = client.post("/api/auth/liff", json={"id_token": "dev:Uabc"})
    assert response.status_code == 401
    assert client.get("/api/dev/line/outbox").status_code == 404


def test_frontend_cannot_claim_identity(client, world):
    """前端傳入的 user_id／role 不被採用：只有 token 決定身分。"""
    headers = login_liff(client, "cg1")
    response = client.post("/api/qa/ask", headers=headers, json={
        "question": "照護紀錄要保存多久？", "client_request_id": new_id(),
        "user_id": str(world.ids["sup_pine"]), "role": "admin"})
    assert response.status_code == 200
    assert client.get("/api/me", headers=headers).json()["role"] == "caregiver"
    assert client.get("/api/admin/cases", headers={"Authorization": "Bearer forged"}).status_code == 401


def test_binding_flow(client, world):
    from app.auth import create_binding_code
    from app.models import User

    session = new_session()
    admin = session.get(User, world.ids["admin_happy"])
    cg2 = session.get(User, world.ids["cg2"])
    code = create_binding_code(session, admin, cg2)
    session.commit()
    session.close()
    token = "dev:U" + "c" * 32
    assert client.post("/api/auth/liff", json={"id_token": token}).json()["status"] == "needs_binding"
    bad = client.post("/api/auth/liff/bind", json={"id_token": token, "binding_code": "WRONGCODE"})
    assert bad.status_code == 400
    ok = client.post("/api/auth/liff/bind", json={"id_token": token, "binding_code": code}).json()
    assert ok["status"] == "ok" and ok["user"]["username"] == "cg2"
    # 綁定碼一次性
    again = client.post("/api/auth/liff/bind", json={"id_token": "dev:U" + "d" * 32, "binding_code": code})
    assert again.status_code == 400
