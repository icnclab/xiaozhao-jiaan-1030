"""BA 服務項目核准 API：僅主任／admin 可切換 reviewed；督導與照服員不可；
核准後才會出現在一般照服員看到的 /service-catalog（reviewed_only）清單。
"""
from __future__ import annotations

from app.db import new_session
from app.models import User
from tests.conftest import PASSWORD, login_liff, login_web, set_password


def _make_director(org_id, username: str = "director_happy") -> None:
    session = new_session()
    user = User(org_id=org_id, username=username, display_name="示範主任", role="director")
    set_password(user, PASSWORD)
    session.add(user)
    session.commit()
    session.close()


def test_supervisor_cannot_approve_ba_service(client, world):
    sup = login_web(client, "sup_a")
    r = client.post("/api/jiaan1030/ba-services/BA01/approve", headers=sup, json={"reviewed": True})
    assert r.status_code == 403, r.text


def test_caregiver_cannot_approve_ba_service(client, world):
    cg = login_liff(client, "cg1")
    r = client.post("/api/jiaan1030/ba-services/BA01/approve", headers=cg, json={"reviewed": True})
    assert r.status_code == 403, r.text


def test_director_can_approve_and_unapprove_ba_service(client, world):
    admin = login_web(client, "admin_happy")
    seeded = client.get("/api/jiaan1030/service-catalog/review", headers=admin)
    assert seeded.status_code == 200, seeded.text
    codes = [r["code"] for r in seeded.json()["ba_services"]]
    if not codes:
        # 這批測試世界沒有預先建好的 BA 資料時，直接補一筆最小資料，不依賴正式庫內容。
        session = new_session()
        from sqlalchemy import text
        session.execute(text(
            "INSERT INTO jiaan1030_ba_services (slot, code, name, reviewed) VALUES (1, 'BA01', '測試服務項目', FALSE)"
        ))
        session.commit()
        session.close()
        codes = ["BA01"]
    code = codes[0]

    _make_director(admin_org_id(client, admin))
    director = login_web(client, "director_happy")

    approved = client.post(f"/api/jiaan1030/ba-services/{code}/approve", headers=director, json={"reviewed": True})
    assert approved.status_code == 200, approved.text
    assert approved.json()["reviewed"] is True

    public = client.get("/api/jiaan1030/service-catalog", headers=login_liff(client, "cg1"))
    assert code in [r["code"] for r in public.json()["ba_services"]]

    unapproved = client.post(f"/api/jiaan1030/ba-services/{code}/approve", headers=director, json={"reviewed": False})
    assert unapproved.status_code == 200
    assert unapproved.json()["reviewed"] is False
    public2 = client.get("/api/jiaan1030/service-catalog", headers=login_liff(client, "cg1"))
    assert code not in [r["code"] for r in public2.json()["ba_services"]]


def test_approve_unknown_code_returns_404(client, world):
    admin = login_web(client, "admin_happy")
    r = client.post("/api/jiaan1030/ba-services/NOPE/approve", headers=admin, json={"reviewed": True})
    assert r.status_code == 404, r.text


def admin_org_id(client, admin_headers):
    me = client.get("/api/me", headers=admin_headers)
    assert me.status_code == 200
    return me.json()["org"]["id"]
