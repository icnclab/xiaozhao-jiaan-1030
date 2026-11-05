"""GA09／SC09 共用表單欄位規格（v2，依紙本修復）：確認資料來源、可回復套用、LIFF 可渲染、未核准禁止送出。

依 `docs/jiaan1030_forms/678412_0.jpg`、`678413_0.jpg` 原始紙本照片修復欄位結構。其餘細節
（必填、字數上限、簽署流程、一表多組彙總格式）未確認，一律保留 required=False 與保守型別，
不自行編造。本檔不重跑 test_jiaan1030_service_drafts.py 已驗證過的授權/角色矩陣，只新增與
「實際欄位內容」直接相關的驗證。
"""

from __future__ import annotations

import json

from sqlalchemy import text

from app.db import new_session
from app.services.jiaan1030_ga09_sc09_fields import SERVICE_CONTENT_ITEMS, apply_draft_fields, ga09_sc09_v2_fields
from tests.conftest import login_liff, login_web, new_id

EXPECTED_FIELD_KEYS = {
    "district", "ltc_level", "welfare_status", "service_type", "service_date",
    "start_time", "end_time", "service_items", "other_service_note", "signature",
}


def _seed_form(code: str, reviewed: bool, schema_status: str, fields_json: dict | None = None) -> None:
    session = new_session()
    session.execute(text(
        "INSERT INTO jiaan1030_service_forms (code, title, fields_json, reviewed, schema_status) "
        "VALUES (:code, :title, :fields_json, :reviewed, :schema_status)"
    ), {
        "code": code, "title": "居家喘息服務" if code == "GA09" else "短照服務",
        "fields_json": json.dumps(fields_json or {}), "reviewed": reviewed, "schema_status": schema_status,
    })
    session.commit()
    session.close()


def _fields_json_in_db(code: str) -> dict:
    session = new_session()
    row = session.execute(text("SELECT fields_json FROM jiaan1030_service_forms WHERE code = :code"),
                          {"code": code}).mappings().first()
    session.close()
    return row["fields_json"]


def test_v2_fields_match_paper_form_and_keep_safe_defaults():
    """v2 欄位規格對應紙本原件的 10 個欄位，且未確認屬性一律保守預設。"""
    spec = ga09_sc09_v2_fields()
    keys = {f["key"] for section in spec["sections"] for f in section["fields"]}
    assert keys == EXPECTED_FIELD_KEYS
    for section in spec["sections"]:
        for field in section["fields"]:
            assert field["required"] is False, f"{field['key']} 必填條件未確認，不可預設為必填"
    signature_field = next(f for s in spec["sections"] for f in s["fields"] if f["key"] == "signature")
    assert signature_field["type"] == "signature_placeholder"
    service_type_field = next(f for s in spec["sections"] for f in s["fields"] if f["key"] == "service_type")
    assert service_type_field["options"] == ["GA09－居家喘息服務", "SC09－居家短照服務"]
    service_items_field = next(f for s in spec["sections"] for f in s["fields"] if f["key"] == "service_items")
    assert service_items_field["type"] == "checkbox_group"
    assert service_items_field["options"] == list(SERVICE_CONTENT_ITEMS)
    assert len(SERVICE_CONTENT_ITEMS) == 13
    ltc_level_field = next(f for s in spec["sections"] for f in s["fields"] if f["key"] == "ltc_level")
    assert ltc_level_field["options"] == [str(n) for n in range(1, 9)]
    start_time_field = next(f for s in spec["sections"] for f in s["fields"] if f["key"] == "start_time")
    assert start_time_field["type"] == "time"


def test_apply_draft_fields_writes_to_unapproved_form():
    """未核准表單可安全套用 v2 欄位（schema_status 仍維持草稿狀態，不自動變更）。"""
    _seed_form("GA09_PENDING_TEST", reviewed=False, schema_status="draft_unverified", fields_json={})
    session = new_session()
    outcome = apply_draft_fields(session, "GA09_PENDING_TEST", ga09_sc09_v2_fields())
    session.commit()
    session.close()
    assert outcome == "applied"
    stored = _fields_json_in_db("GA09_PENDING_TEST")
    assert {f["key"] for s in stored["sections"] for f in s["fields"]} == EXPECTED_FIELD_KEYS


def test_apply_draft_fields_refuses_to_overwrite_approved_form():
    """已核准（schema_status='approved'）的表單，一律拒絕覆蓋，確保資料可回復、不覆蓋已核准內容。"""
    sentinel = {"version": 1, "sections": [{"key": "already_approved", "label": "已核准版本", "fields": []}]}
    _seed_form("SC09_APPROVED_TEST", reviewed=True, schema_status="approved", fields_json=sentinel)
    session = new_session()
    outcome = apply_draft_fields(session, "SC09_APPROVED_TEST", ga09_sc09_v2_fields())
    session.commit()
    session.close()
    assert outcome == "skipped_approved"
    stored = _fields_json_in_db("SC09_APPROVED_TEST")
    assert stored == sentinel, "已核准內容被覆蓋，違反不可覆蓋已核准內容的要求"


def test_apply_draft_fields_not_found_form():
    session = new_session()
    outcome = apply_draft_fields(session, "NOPE", ga09_sc09_v2_fields())
    session.rollback()
    session.close()
    assert outcome == "not_found"


def test_review_catalog_exposes_draft_fields_but_stays_unreviewed(client, world):
    """草稿欄位可供主任審核（/review 可見），但 reviewed 仍是 FALSE、schema_status 仍是草稿狀態，
    一般照服員走 /service-catalog（僅回 reviewed=TRUE）看不到這份未核准的草稿欄位。"""
    _seed_form("GA09_REVIEW_TEST", reviewed=False, schema_status="draft_unverified", fields_json={})
    session = new_session()
    apply_draft_fields(session, "GA09_REVIEW_TEST", ga09_sc09_v2_fields())
    session.commit()
    session.close()

    director = login_web(client, "admin_happy")
    review = client.get("/api/jiaan1030/service-catalog/review", headers=director).json()
    ga09 = next(f for f in review["service_forms"] if f["code"] == "GA09_REVIEW_TEST")
    assert ga09["reviewed"] is False
    assert ga09["schema_status"] == "draft_unverified"
    assert {f["key"] for s in ga09["fields"]["sections"] for f in s["fields"]} == EXPECTED_FIELD_KEYS

    cg = login_liff(client, "cg1")
    public = client.get("/api/jiaan1030/service-catalog", headers=cg).json()
    assert all(f["code"] != "GA09_REVIEW_TEST" for f in public["service_forms"])


def test_draft_with_v2_fields_still_blocked_from_submit(client, world):
    """即使草稿已填入依紙本修復的真實欄位內容，表單仍未核准，送出仍須被擋（409）。"""
    _seed_form("GA09_SUBMIT_TEST", reviewed=False, schema_status="draft_unverified", fields_json={})
    session = new_session()
    apply_draft_fields(session, "GA09_SUBMIT_TEST", ga09_sc09_v2_fields())
    session.commit()
    session.close()

    cg = login_liff(client, "cg1")
    service_client = client.post("/api/jiaan1030/service-clients", headers=cg,
                                 json={"display_label": "測試個案（假資料）"}).json()
    payload = {
        "district": "測試區測試里（假資料）",
        "ltc_level": "5",
        "welfare_status": "一般",
        "service_type": "GA09－居家喘息服務",
        "service_date": "2026-11-01",
        "start_time": "14:00",
        "end_time": "16:00",
        "service_items": ["協助如廁", "陪同運動"],
        "other_service_note": "",
    }
    draft = client.post("/api/jiaan1030/service-drafts", headers=cg, json={
        "service_client_id": service_client["id"], "form_code": "GA09_SUBMIT_TEST", "payload": payload,
        "client_request_id": new_id()}).json()
    assert draft["payload"] == payload

    blocked = client.post(f"/api/jiaan1030/service-drafts/{draft['id']}/submit", headers=cg)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "form_not_approved"
