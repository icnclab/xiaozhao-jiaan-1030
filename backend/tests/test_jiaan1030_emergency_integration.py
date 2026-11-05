import uuid
from sqlalchemy import text
from app.db import new_session
from tests.conftest import login_liff, login_web

BASE = "/api/jiaan1030/emergencies"

def test_emergency_full_http_lifecycle(client, world):
    caregiver = login_liff(client, "cg1")
    supervisor = login_web(client, "sup_a")
    other_supervisor = login_web(client, "sup_b")
    outsider = login_liff(client, "cg_pine")

    # 測試帳號原本是虛構帳號，暫改成符合嘉安角色守衛的名稱
    db = new_session()
    try:
        for key, name in (
            ("cg1", "jiaan_test_cg1"),
            ("sup_a", "jiaan_test_sup_a"),
            ("sup_b", "jiaan_test_sup_b"),
            ("cg_pine", "jiaan_test_cg_pine"),
        ):
            db.execute(
                text("UPDATE users SET username=:name WHERE id=:id"),
                {"name": name, "id": world.ids[key]}
            )
        db.commit()
    finally:
        db.close()

    req = str(uuid.uuid4())
    eid = None

    try:
        # 建立
        created = client.post(
            BASE, headers=caregiver,
            json={"category": "fall", "client_request_id": req}
        )
        assert created.status_code == 201, created.text
        body = created.json()
        eid = body["id"]
        assert body["status"] == "open"
        assert body["delivery"] == "web_poll_only"

        # 重送不能建立第二筆
        repeated = client.post(
            BASE, headers=caregiver,
            json={"category": "fall", "client_request_id": req}
        )
        assert repeated.status_code == 201, repeated.text
        assert repeated.json()["id"] == eid

        # 同一請求編號不得更換分類
        conflict = client.post(
            BASE, headers=caregiver,
            json={"category": "injury", "client_request_id": req}
        )
        assert conflict.status_code == 409, conflict.text

        # 跨機構不得看到通報
        outside_list = client.get(
            BASE + "?status=all", headers=outsider
        )
        assert outside_list.status_code == 200
        assert eid not in {
            item["id"] for item in outside_list.json()["items"]
        }

        # 照服員不能接手
        denied = client.post(
            BASE + f"/{eid}/acknowledge",
            headers=caregiver,
            json={"client_request_id": str(uuid.uuid4())}
        )
        assert denied.status_code == 403, denied.text

        # 未接手不能直接結案
        premature = client.post(
            BASE + f"/{eid}/resolve",
            headers=supervisor,
            json={"client_request_id": str(uuid.uuid4())}
        )
        assert premature.status_code == 409, premature.text

        # 居督接手
        ack = client.post(
            BASE + f"/{eid}/acknowledge",
            headers=supervisor,
            json={"client_request_id": str(uuid.uuid4())}
        )
        assert ack.status_code == 200, ack.text
        assert ack.json()["status"] == "acknowledged"
        # 居督工作台／主任工作台需要顯示「誰接手」，不只是 ID。
        assert ack.json()["acknowledged_by_name"] == "sup_a"

        # 其他居督不可搶接
        takeover = client.post(
            BASE + f"/{eid}/acknowledge",
            headers=other_supervisor,
            json={"client_request_id": str(uuid.uuid4())}
        )
        assert takeover.status_code == 409, takeover.text

        # 原居督結案
        resolved = client.post(
            BASE + f"/{eid}/resolve",
            headers=supervisor,
            json={"client_request_id": str(uuid.uuid4())}
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "resolved"
        assert resolved.json()["resolved_by_name"] == "sup_a"

        # 驗證真實 DB 紀錄與事件歷程
        history = client.get(
            BASE + f"/{eid}/history", headers=supervisor
        )
        assert history.status_code == 200, history.text
        events = [
            x["event_type"] for x in history.json()["items"]
        ]
        assert events == ["created", "acknowledged", "resolved"]
        actor_names = [x["actor_name"] for x in history.json()["items"]]
        assert actor_names == ["cg1", "sup_a", "sup_a"]

        db = new_session()
        try:
            row = db.execute(
                text("SELECT status FROM jiaan1030_emergencies WHERE id=:id"),
                {"id": uuid.UUID(eid)}
            ).scalar_one()
            assert row == "resolved"
        finally:
            db.close()

    finally:
        # 只刪除本次測試產生的緊急通報與事件，不清除其他緊急通報
        if eid:
            db = new_session()
            try:
                db.execute(
                    text("DELETE FROM jiaan1030_emergency_events WHERE emergency_id=:id"),
                    {"id": uuid.UUID(eid)}
                )
                db.execute(
                    text("DELETE FROM jiaan1030_emergencies WHERE id=:id"),
                    {"id": uuid.UUID(eid)}
                )
                db.commit()
            finally:
                db.close()
