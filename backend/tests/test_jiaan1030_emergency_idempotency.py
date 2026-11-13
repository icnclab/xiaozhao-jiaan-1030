"""2026-11-13 SOS batch: the existing test_jiaan1030_emergency_integration.py
already covers create-dedup, cross-org isolation, role denial, premature
resolve, and a DIFFERENT supervisor being blocked from taking over an
acknowledged case. The one invariant it does not exercise is the SAME actor
re-sending acknowledge/resolve (double-click / retry-after-timeout from the
SOS APP's own confirm() flow) -- this must be a no-op, not a duplicate event
or an error, per app/api/jiaan1030_emergency_routes.py:178-220.
"""
import uuid
from sqlalchemy import text
from app.db import new_session
from tests.conftest import login_liff, login_web

BASE = "/api/jiaan1030/emergencies"


def test_repeat_acknowledge_and_resolve_by_the_same_actor_is_idempotent(client, world):
    caregiver = login_liff(client, "cg1")
    supervisor = login_web(client, "sup_a")

    req = str(uuid.uuid4())
    eid = None
    try:
        created = client.post(BASE, headers=caregiver, json={"category": "fall", "client_request_id": req})
        assert created.status_code == 201, created.text
        eid = created.json()["id"]

        first_ack = client.post(BASE + f"/{eid}/acknowledge", headers=supervisor,
                                 json={"client_request_id": str(uuid.uuid4())})
        assert first_ack.status_code == 200, first_ack.text
        assert first_ack.json()["status"] == "acknowledged"

        # Same supervisor re-sends acknowledge (double-click / retry): no error, no new event.
        second_ack = client.post(BASE + f"/{eid}/acknowledge", headers=supervisor,
                                  json={"client_request_id": str(uuid.uuid4())})
        assert second_ack.status_code == 200, second_ack.text
        assert second_ack.json()["status"] == "acknowledged"
        assert second_ack.json()["acknowledged_by_name"] == "sup_a"

        first_resolve = client.post(BASE + f"/{eid}/resolve", headers=supervisor,
                                     json={"client_request_id": str(uuid.uuid4())})
        assert first_resolve.status_code == 200, first_resolve.text
        assert first_resolve.json()["status"] == "resolved"

        # Already-resolved event re-sent again: idempotent 200, not a 409/500.
        second_resolve = client.post(BASE + f"/{eid}/resolve", headers=supervisor,
                                      json={"client_request_id": str(uuid.uuid4())})
        assert second_resolve.status_code == 200, second_resolve.text
        assert second_resolve.json()["status"] == "resolved"

        # Exactly one acknowledged + one resolved event recorded, despite two
        # calls each -- the repeat calls must not create duplicate history rows.
        history = client.get(BASE + f"/{eid}/history", headers=supervisor)
        assert history.status_code == 200, history.text
        events = [x["event_type"] for x in history.json()["items"]]
        assert events == ["created", "acknowledged", "resolved"], events
    finally:
        if eid:
            db = new_session()
            try:
                db.execute(text("DELETE FROM jiaan1030_emergency_events WHERE emergency_id=:id"), {"id": uuid.UUID(eid)})
                db.execute(text("DELETE FROM jiaan1030_emergencies WHERE id=:id"), {"id": uuid.UUID(eid)})
                db.commit()
            finally:
                db.close()


def test_admin_may_resolve_a_case_acknowledged_by_a_different_supervisor(client, world):
    """app/api/jiaan1030_emergency_routes.py:210 explicitly exempts
    director/admin from the handoff_owner_only check -- confirm that
    exemption actually works end-to-end (it is currently only exercised
    implicitly, never asserted directly by name). world's fixture has no
    director user, so this uses admin_happy -- the other role in the same
    exemption clause."""
    caregiver = login_liff(client, "cg1")
    supervisor = login_web(client, "sup_a")
    director = login_web(client, "admin_happy")

    req = str(uuid.uuid4())
    eid = None
    try:
        created = client.post(BASE, headers=caregiver, json={"category": "fall", "client_request_id": req})
        assert created.status_code == 201, created.text
        eid = created.json()["id"]

        ack = client.post(BASE + f"/{eid}/acknowledge", headers=supervisor,
                           json={"client_request_id": str(uuid.uuid4())})
        assert ack.status_code == 200, ack.text

        resolved_by_director = client.post(BASE + f"/{eid}/resolve", headers=director,
                                            json={"client_request_id": str(uuid.uuid4())})
        assert resolved_by_director.status_code == 200, resolved_by_director.text
        assert resolved_by_director.json()["status"] == "resolved"
        assert resolved_by_director.json()["resolved_by_name"] == "admin_happy"
    finally:
        if eid:
            db = new_session()
            try:
                db.execute(text("DELETE FROM jiaan1030_emergency_events WHERE emergency_id=:id"), {"id": uuid.UUID(eid)})
                db.execute(text("DELETE FROM jiaan1030_emergencies WHERE id=:id"), {"id": uuid.UUID(eid)})
                db.commit()
            finally:
                db.close()
