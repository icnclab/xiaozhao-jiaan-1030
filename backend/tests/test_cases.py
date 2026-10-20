"""A7／A9：分類回報到正確督導、督導回覆回到照服員、通知失敗可追蹤與重送。"""

from __future__ import annotations

from sqlalchemy import select

from app.db import new_session
from app.line.client import MockLineClient
from app.models import LineMockOutbox, NotificationJob
from app.worker import drain
from tests.conftest import login_liff, login_web, new_id


def quick_report(client, headers, world, category="家屬額外要求", text="家屬要我幫住民代購成藥"):
    categories = client.get("/api/categories", headers=headers).json()
    cat = next(c for c in categories if c["name"] == category)
    return client.post("/api/cases", headers=headers, json={
        "category_id": cat["id"], "template_id": cat["templates"][0]["id"], "text": text,
        "client_request_id": new_id()})


def test_category_routing_and_reply(client, world):
    cg = login_liff(client, "cg1")
    response = quick_report(client, cg, world)
    assert response.status_code == 200, response.text
    case = response.json()
    assert case["assignee"]["id"] == str(world.ids["sup_a"])  # 家屬額外要求 → 督導 A
    assert case["status"] == "pending"
    moved = quick_report(client, cg, world, category="移位與行動協助", text="移位要幾個人").json()
    assert moved["assignee"]["id"] == str(world.ids["sup_b"])
    other = quick_report(client, cg, world, category="其他", text="其他問題").json()
    assert other["assignee"] is None  # 未設定預設督導 → 共用待處理區

    sup = login_web(client, "sup_a")
    listing = client.get("/api/admin/cases?status=pending", headers=sup).json()
    assert {c["number"] for c in listing} >= {case["number"]}
    client.post(f"/api/admin/cases/{case['id']}/take", headers=sup)
    reply = client.post(f"/api/admin/cases/{case['id']}/reply", headers=sup,
                        json={"text": "藥品一律不代購，請家屬自行購買交護理站", "client_request_id": new_id()}).json()
    assert reply["reply_saved"] and reply["notification"]["status"] == "queued"
    drain()
    # 照服員端看得到回覆與狀態
    mine = client.get("/api/cases/mine", headers=cg).json()
    target = next(c for c in mine if c["id"] == case["id"])
    assert target["status"] == "replied" and target["has_reply"]
    detail = client.get(f"/api/cases/{case['id']}", headers=cg).json()
    assert any("不代購" in m["body"] for m in detail["messages"])
    assert "events" not in detail  # 照服員看不到內部歷程
    # 推播只帶案件編號與連結，不帶回覆全文
    session = new_session()
    push = session.scalar(select(LineMockOutbox).where(LineMockOutbox.kind == "push"))
    assert case["number"] in push.messages[0]["text"] and "不代購" not in push.messages[0]["text"]
    assert session.scalar(select(NotificationJob.status)) == "accepted"
    session.close()
    closed = client.post(f"/api/admin/cases/{case['id']}/close", headers=sup, json={"reason": "已回覆"}).json()
    assert closed["status"] == "closed"


def test_reply_idempotent(client, world):
    cg = login_liff(client, "cg1")
    case = quick_report(client, cg, world).json()
    sup = login_web(client, "sup_a")
    rid = new_id()
    for _ in range(2):
        client.post(f"/api/admin/cases/{case['id']}/reply", headers=sup, json={"text": "好", "client_request_id": rid})
    detail = client.get(f"/api/admin/cases/{case['id']}", headers=sup).json()
    assert len([m for m in detail["messages"] if m["author_role"] == "supervisor"]) == 1
    assert len(detail["notifications"]) == 1


def test_notification_failure_tracked_and_retry(client, world):
    """A9：push 失敗（429 額度）→ failed＋錯誤碼可見；回覆本身不丟；重送後 accepted。"""
    cg = login_liff(client, "cg1")
    case = quick_report(client, cg, world).json()
    sup = login_web(client, "sup_a")
    MockLineClient.force_push_status = 400  # 不可重試的錯誤
    client.post(f"/api/admin/cases/{case['id']}/reply", headers=sup, json={"text": "請稍候", "client_request_id": new_id()})
    drain()
    notes = client.get("/api/admin/notifications?status=failed", headers=sup).json()
    assert len(notes) == 1 and notes[0]["last_error_code"] == "bad_request"
    assert any(m["body"] == "請稍候" for m in client.get(f"/api/cases/{case['id']}", headers=cg).json()["messages"])
    MockLineClient.force_push_status = None
    client.post(f"/api/admin/notifications/{notes[0]['id']}/retry", headers=sup)
    drain()
    session = new_session()
    notification = session.scalar(select(NotificationJob))
    assert notification.status == "accepted"
    session.close()


def test_caregiver_without_line_gets_skipped_notification(client, world):
    from app.models import User
    from app.services import cases

    session = new_session()
    cg2 = session.get(User, world.ids["cg2"])  # 沒有綁定 LINE
    case, _ = cases.create_case(session, cg2, source="quick_report", summary_masked="x", reason="x",
                                client_request_id="abcdefgh-1", category_id=world.ids["cat:HAPPY:其他"])
    session.commit()
    case_id = case.id
    session.close()
    sup = login_web(client, "sup_a")
    body = client.post(f"/api/admin/cases/{case_id}/reply", headers=sup,
                       json={"text": "收到", "client_request_id": new_id()}).json()
    assert body["notification"]["status"] == "skipped"
    assert body["notification"]["last_error_code"] == "no_line_account"


def test_invalid_transition_rejected(client, world):
    cg = login_liff(client, "cg1")
    case = quick_report(client, cg, world).json()
    sup = login_web(client, "sup_a")
    client.post(f"/api/admin/cases/{case['id']}/close", headers=sup, json={"reason": "重複"})
    response = client.post(f"/api/admin/cases/{case['id']}/reply", headers=sup,
                           json={"text": "x", "client_request_id": new_id()})
    assert response.status_code == 409


def test_caregiver_followup_reopens(client, world):
    cg = login_liff(client, "cg1")
    case = quick_report(client, cg, world).json()
    sup = login_web(client, "sup_a")
    client.post(f"/api/admin/cases/{case['id']}/reply", headers=sup, json={"text": "好", "client_request_id": new_id()})
    detail = client.post(f"/api/cases/{case['id']}/messages", headers=cg,
                         json={"body": "家屬王先生還是堅持", "client_request_id": new_id()}).json()
    assert detail["status"] == "in_progress"
    assert all("王先生" not in m["body"] for m in detail["messages"])
