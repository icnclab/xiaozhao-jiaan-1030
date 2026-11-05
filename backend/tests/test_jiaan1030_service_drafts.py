"""GA09/SC09 服務紀錄草稿：建立/更新/送出、角色權限、未核准表單禁止送出、稽核紀錄。

草稿關聯獨立的服務個案主檔（jiaan1030_service_clients），不是 cases（督導問題回報工單）。
涵蓋：服務個案存取政策（建立者可讀寫；督導/主任/admin 須同機構且有明確授權才可唯讀）、
跨機構存取、非建立者未授權更新/送出、重複送出（併發/重送）、
主任核准前置條件（schema_status 必須先核准才可 reviewed=TRUE）、督導不可呼叫核准 API。

本階段僅使用假資料（display_label 為測試用代稱），不處理真實長者資料、照片或簽章。
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select, text

from app.db import new_session
from app.models import AuditLog, LineAccount, User
from tests.conftest import line_id, login_liff, login_web, new_id


def _bind_line(user_id) -> None:
    """讓測試世界裡尚未綁定 LINE 的照服員也能用 login_liff 登入（假資料，供跨居督共用測試）。"""
    session = new_session()
    user = session.get(User, user_id)
    existing = session.query(LineAccount).filter_by(user_id=user.id).first()
    if existing is None:
        session.add(LineAccount(user_id=user.id, line_user_id=line_id(user.username)))
        session.commit()
    session.close()


def _seed_form(code: str = "GA09", reviewed: bool = False, schema_status: str = "draft_unverified") -> None:
    session = new_session()
    session.execute(text(
        "INSERT INTO jiaan1030_service_forms (code, title, fields_json, reviewed, schema_status) "
        "VALUES (:code, :title, '{}'::jsonb, :reviewed, :schema_status)"
    ), {"code": code, "title": "居家喘息服務", "reviewed": reviewed, "schema_status": schema_status})
    session.commit()
    session.close()


def _make_client(client, headers, label: str = "測試個案甲（假資料）"):
    created = client.post("/api/jiaan1030/service-clients", headers=headers, json={"display_label": label})
    assert created.status_code == 201, created.text
    return created.json()


def test_create_update_draft_and_block_submit_until_approved(client, world):
    _seed_form()
    cg = login_liff(client, "cg1")
    service_client = _make_client(client, cg)
    created = client.post("/api/jiaan1030/service-drafts", headers=cg, json={
        "service_client_id": service_client["id"], "form_code": "GA09",
        "payload": {"note": "first"}, "client_request_id": new_id()})
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["status"] == "draft"
    assert draft["service_client_id"] == service_client["id"]

    updated = client.patch(f"/api/jiaan1030/service-drafts/{draft['id']}", headers=cg,
                           json={"payload": {"note": "second"}})
    assert updated.status_code == 200, updated.text
    assert updated.json()["payload"] == {"note": "second"}

    blocked = client.post(f"/api/jiaan1030/service-drafts/{draft['id']}/submit", headers=cg)
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == "form_not_approved"

    director = login_web(client, "admin_happy")
    approve_schema = client.post("/api/jiaan1030/service-forms/GA09/approve", headers=director,
                                 json={"schema_status": "approved"})
    assert approve_schema.status_code == 200, approve_schema.text
    approve_reviewed = client.post("/api/jiaan1030/service-forms/GA09/approve", headers=director,
                                   json={"reviewed": True})
    assert approve_reviewed.status_code == 200, approve_reviewed.text

    submitted = client.post(f"/api/jiaan1030/service-drafts/{draft['id']}/submit", headers=cg)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"

    cannot_edit = client.patch(f"/api/jiaan1030/service-drafts/{draft['id']}", headers=cg,
                               json={"payload": {"note": "third"}})
    assert cannot_edit.status_code == 409

    session = new_session()
    actions = {a.action for a in session.scalars(select(AuditLog).where(
        AuditLog.target_type == "jiaan1030_service_form_draft"))}
    session.close()
    assert {"jiaan1030_draft.create", "jiaan1030_draft.update", "jiaan1030_draft.submit"} <= actions


def test_create_draft_idempotent_by_client_request_id(client, world):
    _seed_form()
    cg = login_liff(client, "cg1")
    service_client = _make_client(client, cg)
    body = {"service_client_id": service_client["id"], "form_code": "GA09",
            "payload": {"note": "a"}, "client_request_id": new_id()}
    first = client.post("/api/jiaan1030/service-drafts", headers=cg, json=body).json()
    second = client.post("/api/jiaan1030/service-drafts", headers=cg, json=body).json()
    assert first["id"] == second["id"]


def test_create_draft_concurrent_duplicate_request_does_not_500(client, world):
    """1030 嘉安場域實測發現：ServiceFormPage 首次載入時（React StrictMode 雙重掛載，
    或行動網路重送）會以同一 client_request_id 幾乎同時送出兩次建立草稿請求，
    觸發唯一索引衝突，若未攔截會回 500 並在畫面顯示「系統目前無法完成回答」。
    兩個請求應都成功，且回傳同一筆草稿，不應有任一請求收到 500。"""
    _seed_form()
    cg = login_liff(client, "cg1")
    service_client = _make_client(client, cg)
    body = {"service_client_id": service_client["id"], "form_code": "GA09",
            "payload": {}, "client_request_id": new_id()}
    barrier = threading.Barrier(2)

    def fire():
        barrier.wait(timeout=5)
        return client.post("/api/jiaan1030/service-drafts", headers=cg, json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        r1, r2 = [f.result() for f in [pool.submit(fire), pool.submit(fire)]]

    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    assert r1.json()["id"] == r2.json()["id"]


def test_caregiver_cannot_approve_form(client, world):
    _seed_form()
    cg = login_liff(client, "cg1")
    response = client.post("/api/jiaan1030/service-forms/GA09/approve", headers=cg,
                           json={"schema_status": "approved"})
    assert response.status_code == 403


def test_caregiver_cannot_edit_others_draft(client, world):
    """同機構、非自己建立且未被授權的草稿，照服員不可修改。"""
    _seed_form()
    cg1 = login_liff(client, "cg1")
    service_client = _make_client(client, cg1)
    draft = client.post("/api/jiaan1030/service-drafts", headers=cg1, json={
        "service_client_id": service_client["id"], "form_code": "GA09", "payload": {},
        "client_request_id": new_id()}).json()
    other_cg = login_liff(client, "cg_pine")
    response = client.patch(f"/api/jiaan1030/service-drafts/{draft['id']}", headers=other_cg, json={"payload": {"x": 1}})
    assert response.status_code == 404


def test_supervisor_without_grant_cannot_see_draft_or_client(client, world):
    """沒有明確授權時，督導即使同機構也看不到草稿或服務個案（保守預設）。"""
    _seed_form()
    cg = login_liff(client, "cg1")
    service_client = _make_client(client, cg)
    draft = client.post("/api/jiaan1030/service-drafts", headers=cg, json={
        "service_client_id": service_client["id"], "form_code": "GA09", "payload": {},
        "client_request_id": new_id()}).json()
    sup = login_web(client, "sup_a")
    listing = client.get("/api/jiaan1030/service-drafts", headers=sup).json()
    assert all(d["id"] != draft["id"] for d in listing)
    clients_listing = client.get("/api/jiaan1030/service-clients", headers=sup).json()
    assert all(c["id"] != service_client["id"] for c in clients_listing)
    edit_attempt = client.patch(f"/api/jiaan1030/service-drafts/{draft['id']}", headers=sup, json={"payload": {"x": 1}})
    assert edit_attempt.status_code == 404


def test_supervisor_with_grant_can_read_but_not_edit(client, world):
    """建立者明確授權督導後，督導可唯讀草稿與服務個案，但仍不可修改/送出。"""
    _seed_form()
    session = new_session()
    sup_a_id = str(session.get(User, world.ids["sup_a"]).id)
    session.close()
    cg = login_liff(client, "cg1")
    service_client = _make_client(client, cg)
    grant = client.post(f"/api/jiaan1030/service-clients/{service_client['id']}/grants", headers=cg,
                        json={"grantee_id": sup_a_id})
    assert grant.status_code == 201, grant.text

    draft = client.post("/api/jiaan1030/service-drafts", headers=cg, json={
        "service_client_id": service_client["id"], "form_code": "GA09", "payload": {},
        "client_request_id": new_id()}).json()

    sup = login_web(client, "sup_a")
    listing = client.get("/api/jiaan1030/service-drafts", headers=sup).json()
    assert any(d["id"] == draft["id"] for d in listing)
    clients_listing = client.get("/api/jiaan1030/service-clients", headers=sup).json()
    assert any(c["id"] == service_client["id"] for c in clients_listing)
    edit_attempt = client.patch(f"/api/jiaan1030/service-drafts/{draft['id']}", headers=sup, json={"payload": {"x": 1}})
    assert edit_attempt.status_code == 403
    submit_attempt = client.post(f"/api/jiaan1030/service-drafts/{draft['id']}/submit", headers=sup)
    assert submit_attempt.status_code == 403


def test_revoked_grant_removes_supervisor_access(client, world):
    """撤銷授權後，督導立即失去唯讀權限。"""
    _seed_form()
    session = new_session()
    sup_a_id = str(session.get(User, world.ids["sup_a"]).id)
    session.close()
    cg = login_liff(client, "cg1")
    service_client = _make_client(client, cg)
    client.post(f"/api/jiaan1030/service-clients/{service_client['id']}/grants", headers=cg,
               json={"grantee_id": sup_a_id})
    sup = login_web(client, "sup_a")
    assert any(c["id"] == service_client["id"]
              for c in client.get("/api/jiaan1030/service-clients", headers=sup).json())

    revoke = client.post(f"/api/jiaan1030/service-clients/{service_client['id']}/grants/{sup_a_id}/revoke",
                         headers=cg)
    assert revoke.status_code == 200, revoke.text
    assert all(c["id"] != service_client["id"]
              for c in client.get("/api/jiaan1030/service-clients", headers=sup).json())


def test_supervisor_cannot_grant_access_to_self(client, world):
    """督導不能自行授權自己查看服務個案（避免越權自授）；只有建立者或主任/admin 可授權。"""
    _seed_form()
    session = new_session()
    sup_a_id = str(session.get(User, world.ids["sup_a"]).id)
    sup_b_id = str(session.get(User, world.ids["sup_b"]).id)
    session.close()
    cg = login_liff(client, "cg1")
    service_client = _make_client(client, cg)
    sup_a = login_web(client, "sup_a")
    response = client.post(f"/api/jiaan1030/service-clients/{service_client['id']}/grants", headers=sup_a,
                           json={"grantee_id": sup_b_id})
    assert response.status_code == 404  # 督導對未授權的服務個案連存在與否都看不到


def test_cross_org_grantee_rejected(client, world):
    """被授權人若非同機構，授權請求應被拒絕（不可跨機構授權）。"""
    _seed_form()
    session = new_session()
    pine_sup_id = str(session.get(User, world.ids["sup_pine"]).id)
    session.close()
    cg = login_liff(client, "cg1")
    service_client = _make_client(client, cg)
    response = client.post(f"/api/jiaan1030/service-clients/{service_client['id']}/grants", headers=cg,
                           json={"grantee_id": pine_sup_id})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_grantee"


def test_cross_org_draft_update_and_submit_return_404_not_403(client, world):
    """跨機構不只不可見，連「存在與否」都不能洩漏（回 404 而非 403），且不可偽造送出。"""
    _seed_form()
    cg = login_liff(client, "cg1")
    service_client = _make_client(client, cg)
    draft = client.post("/api/jiaan1030/service-drafts", headers=cg, json={
        "service_client_id": service_client["id"], "form_code": "GA09", "payload": {},
        "client_request_id": new_id()}).json()
    pine_sup = login_web(client, "sup_pine")
    assert client.patch(f"/api/jiaan1030/service-drafts/{draft['id']}", headers=pine_sup,
                        json={"payload": {"x": 1}}).status_code == 404
    assert client.post(f"/api/jiaan1030/service-drafts/{draft['id']}/submit", headers=pine_sup).status_code == 404

    session = new_session()
    denied = session.scalars(select(AuditLog).where(
        AuditLog.action == "access_denied", AuditLog.target_type == "jiaan1030_service_form_draft")).all()
    session.close()
    assert len(denied) >= 2


def test_caregiver_cannot_create_draft_on_another_caregivers_client_same_org(client, world):
    """同機構、非自己建立且未被授權的服務個案，照服員不可替它建立草稿（避免冒用他人個案）。"""
    _seed_form()
    cg1 = login_liff(client, "cg1")
    service_client = _make_client(client, cg1)

    cg_pine = login_liff(client, "cg_pine")
    response = client.post("/api/jiaan1030/service-drafts", headers=cg_pine, json={
        "service_client_id": service_client["id"], "form_code": "GA09", "payload": {},
        "client_request_id": new_id()})
    assert response.status_code == 404


def test_submitted_draft_submit_again_is_idempotent_no_duplicate_audit(client, world):
    """已送出的草稿重複呼叫 submit：回同一筆已送出結果，不重複寫入稽核紀錄。"""
    _seed_form(reviewed=True, schema_status="approved")
    cg = login_liff(client, "cg1")
    service_client = _make_client(client, cg)
    draft = client.post("/api/jiaan1030/service-drafts", headers=cg, json={
        "service_client_id": service_client["id"], "form_code": "GA09", "payload": {},
        "client_request_id": new_id()}).json()
    first = client.post(f"/api/jiaan1030/service-drafts/{draft['id']}/submit", headers=cg)
    assert first.status_code == 200 and first.json()["status"] == "submitted"
    second = client.post(f"/api/jiaan1030/service-drafts/{draft['id']}/submit", headers=cg)
    assert second.status_code == 200 and second.json()["status"] == "submitted"

    session = new_session()
    submits = session.scalars(select(AuditLog).where(
        AuditLog.action == "jiaan1030_draft.submit", AuditLog.target_id == draft["id"])).all()
    session.close()
    assert len(submits) == 1


def test_reviewed_cannot_be_set_true_without_schema_approved_first(client, world):
    """主任不能跳過『欄位已人工核對』(schema_status=approved) 就直接核准 reviewed=TRUE。"""
    _seed_form(reviewed=False, schema_status="draft_unverified")
    director = login_web(client, "admin_happy")
    response = client.post("/api/jiaan1030/service-forms/GA09/approve", headers=director, json={"reviewed": True})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "schema_not_approved"


def test_supervisor_cannot_approve_form(client, world):
    """督導可唯讀查看審核中繼資料，但不可呼叫核准 API（僅限主任/admin）。"""
    _seed_form()
    sup = login_web(client, "sup_a")
    response = client.post("/api/jiaan1030/service-forms/GA09/approve", headers=sup, json={"schema_status": "approved"})
    assert response.status_code == 403


# ── 跨居督共用照服員：明確、可撤銷的照服員個案授權 ──────────────────────

def test_granted_caregiver_can_read_client_and_create_own_draft(client, world):
    """同機構、未參與建立的照服員，一旦被明確授權，就能唯讀個案並建立「自己的」草稿（跨居督共用）。"""
    _seed_form()
    _bind_line(world.ids["cg2"])
    cg1 = login_liff(client, "cg1")
    service_client = _make_client(client, cg1)

    cg2 = login_liff(client, "cg2")
    before_grant = client.post("/api/jiaan1030/service-drafts", headers=cg2, json={
        "service_client_id": service_client["id"], "form_code": "GA09", "payload": {},
        "client_request_id": new_id()})
    assert before_grant.status_code == 404

    grant = client.post(f"/api/jiaan1030/service-clients/{service_client['id']}/grants", headers=cg1,
                        json={"grantee_id": world.ids["cg2"].__str__()})
    assert grant.status_code == 201, grant.text

    visible = client.get("/api/jiaan1030/service-clients", headers=cg2).json()
    assert any(c["id"] == service_client["id"] for c in visible)

    created = client.post("/api/jiaan1030/service-drafts", headers=cg2, json={
        "service_client_id": service_client["id"], "form_code": "GA09", "payload": {"note": "cg2 寫的"},
        "client_request_id": new_id()})
    assert created.status_code == 201, created.text
    cg2_draft = created.json()
    assert cg2_draft["status"] == "draft"


def test_caregiver_cannot_edit_or_submit_other_caregivers_draft_even_with_grant(client, world):
    """被授權的照服員能看到個案下其他照服員的草稿，但不能修改或送出（只能動自己建立的）。"""
    _seed_form()
    _bind_line(world.ids["cg2"])
    cg1 = login_liff(client, "cg1")
    service_client = _make_client(client, cg1)
    cg1_draft = client.post("/api/jiaan1030/service-drafts", headers=cg1, json={
        "service_client_id": service_client["id"], "form_code": "GA09", "payload": {},
        "client_request_id": new_id()}).json()

    client.post(f"/api/jiaan1030/service-clients/{service_client['id']}/grants", headers=cg1,
               json={"grantee_id": world.ids["cg2"].__str__()})
    cg2 = login_liff(client, "cg2")

    listing = client.get("/api/jiaan1030/service-drafts", headers=cg2).json()
    assert any(d["id"] == cg1_draft["id"] for d in listing)

    edit_attempt = client.patch(f"/api/jiaan1030/service-drafts/{cg1_draft['id']}", headers=cg2,
                                json={"payload": {"x": 1}})
    assert edit_attempt.status_code == 403
    submit_attempt = client.post(f"/api/jiaan1030/service-drafts/{cg1_draft['id']}/submit", headers=cg2)
    assert submit_attempt.status_code == 403


def test_granted_supervisor_cannot_create_draft_even_with_valid_grant(client, world):
    """督導即使有效授權唯讀個案，也不能建立草稿（唯讀，不得擅自擴權成可寫）。"""
    _seed_form()
    session = new_session()
    sup_a_id = str(session.get(User, world.ids["sup_a"]).id)
    session.close()
    cg1 = login_liff(client, "cg1")
    service_client = _make_client(client, cg1)
    client.post(f"/api/jiaan1030/service-clients/{service_client['id']}/grants", headers=cg1,
               json={"grantee_id": sup_a_id})

    sup = login_web(client, "sup_a")
    response = client.post("/api/jiaan1030/service-drafts", headers=sup, json={
        "service_client_id": service_client["id"], "form_code": "GA09", "payload": {},
        "client_request_id": new_id()})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"

    session = new_session()
    denied = session.scalars(select(AuditLog).where(
        AuditLog.action == "jiaan1030_draft.forbidden", AuditLog.outcome == "denied")).all()
    session.close()
    assert any(d.target_type == "jiaan1030_service_client" for d in denied)


def test_revoked_caregiver_grant_blocks_further_access_and_new_drafts(client, world):
    """撤銷照服員授權後，立即失去唯讀與建立草稿的能力（既有草稿仍留存，不回溯刪除）。"""
    _seed_form()
    _bind_line(world.ids["cg2"])
    cg1 = login_liff(client, "cg1")
    service_client = _make_client(client, cg1)
    client.post(f"/api/jiaan1030/service-clients/{service_client['id']}/grants", headers=cg1,
               json={"grantee_id": world.ids["cg2"].__str__()})

    cg2 = login_liff(client, "cg2")
    assert client.post("/api/jiaan1030/service-drafts", headers=cg2, json={
        "service_client_id": service_client["id"], "form_code": "GA09", "payload": {},
        "client_request_id": new_id()}).status_code == 201

    revoke = client.post(f"/api/jiaan1030/service-clients/{service_client['id']}/grants/{world.ids['cg2']}/revoke",
                         headers=cg1)
    assert revoke.status_code == 200, revoke.text

    blocked = client.post("/api/jiaan1030/service-drafts", headers=cg2, json={
        "service_client_id": service_client["id"], "form_code": "GA09", "payload": {},
        "client_request_id": new_id()})
    assert blocked.status_code == 404
    assert client.get("/api/jiaan1030/service-clients", headers=cg2).json() == [] or all(
        c["id"] != service_client["id"] for c in client.get("/api/jiaan1030/service-clients", headers=cg2).json())


def test_grantee_cannot_be_the_creator_themself(client, world):
    """建立者本身已有完整權限，不需要（也不應該）再對自己額外授權。"""
    _seed_form()
    cg1 = login_liff(client, "cg1")
    service_client = _make_client(client, cg1)
    response = client.post(f"/api/jiaan1030/service-clients/{service_client['id']}/grants", headers=cg1,
                           json={"grantee_id": world.ids["cg1"].__str__()})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_grantee"
