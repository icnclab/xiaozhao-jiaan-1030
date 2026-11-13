"""MPC人工核對是督導／管理層的覆核工具，不是照服員自助功能：照服員應收到403。"""

from __future__ import annotations

import json
from pathlib import Path

from tests.conftest import login_liff, login_web

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[1] / "mpc_test_fixtures" / "handover_payloads_for_backend.json")
    .read_text(encoding="utf-8")
)["CASE_01_BA16_MED"]["api_confirm_payload"]


def test_caregiver_forbidden_from_mpc_endpoints(client, world):
    headers = login_liff(client, "cg1")
    assert client.post("/api/mpc/preview", headers=headers, json=FIXTURE).status_code == 403
    assert client.post("/api/mpc/review-draft", headers=headers,
                       json={"payload": FIXTURE, "review": {}}).status_code == 403


def test_supervisor_and_admin_allowed(client, world):
    for username in ("sup_a", "admin_happy"):
        headers = login_web(client, username)
        preview = client.post("/api/mpc/preview", headers=headers, json=FIXTURE)
        assert preview.status_code == 200, (username, preview.text)
        review = client.post("/api/mpc/review-draft", headers=headers, json={
            "payload": FIXTURE,
            "review": {
                "acknowledge_review": True,
                "selected_idx": preview.json()["selected_idx"],
                "confirmed_summary": preview.json()["summary_suggestion"],
            },
        })
        assert review.status_code == 200, (username, review.text)
