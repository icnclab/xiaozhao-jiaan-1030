"""HTTP E2E for multi-turn Context against an explicitly isolated test API/DB."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import LineAccount, LineMockOutbox, NotificationJob, User


def synthetic_line_id(label: str) -> str:
    return "U" + hashlib.md5(label.encode()).hexdigest()


def prepare_identities(database_url: str) -> dict[str, str]:
    engine = create_engine(database_url)
    identities = {
        "caregiver_owner": ("cg_happy_1", synthetic_line_id("demo:cg_happy_1")),
        "caregiver_peer": ("cg_happy_2", synthetic_line_id("e2e:cg_happy_2")),
        "caregiver_other_org": ("cg_pine_1", synthetic_line_id("demo:cg_pine_1")),
        "supervisor": ("sup_happy_a", synthetic_line_id("e2e:sup_happy_a")),
    }
    try:
        with Session(engine) as session:
            for username, line_id in identities.values():
                user = session.scalar(select(User).where(User.username == username))
                if user is None:
                    raise RuntimeError(f"missing synthetic user: {username}")
                current = session.scalar(select(LineAccount).where(LineAccount.user_id == user.id))
                if current is None:
                    session.add(LineAccount(user_id=user.id, line_user_id=line_id))
            session.commit()
    finally:
        engine.dispose()
    return {key: value[1] for key, value in identities.items()}


def run(base_url: str, database_url: str) -> dict:
    identities = prepare_identities(database_url)
    checks: list[dict] = []
    latencies_ms: list[float] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(condition), "detail": detail})

    with httpx.Client(base_url=base_url, timeout=20) as client:
        def login(key: str) -> dict[str, str]:
            response = client.post("/api/auth/liff", json={"id_token": "dev:" + identities[key]})
            check(f"login:{key}", response.status_code == 200, str(response.status_code))
            return {"Authorization": "Bearer " + response.json()["session_token"]}

        owner = login("caregiver_owner")
        peer = login("caregiver_peer")
        other_org = login("caregiver_other_org")
        supervisor = login("supervisor")

        def post_qa(headers: dict[str, str], payload: dict) -> httpx.Response:
            started = time.perf_counter()
            response = client.post("/api/qa/ask", headers=headers, json=payload)
            latencies_ms.append((time.perf_counter() - started) * 1000)
            return response

        first_request = str(uuid.uuid4())
        first_body = {
            "question": "夜間每多少位住民要配置一名照服員？",
            "source": "text",
            "client_request_id": first_request,
        }
        first = post_qa(owner, first_body)
        first_json = first.json()
        check("new_question_http_200", first.status_code == 200, str(first.status_code))
        check("new_question_has_conversation", bool(first_json.get("conversation_id")))
        check("rag_citations_present", bool(first_json.get("citations")), first_json.get("outcome", ""))
        conversation_id = first_json["conversation_id"]

        detail = client.get(f"/api/interactions/{conversation_id}", headers=owner)
        check("new_question_created_interaction", detail.status_code == 200, str(detail.status_code))
        check("interaction_has_one_question", detail.json().get("question_count") == 1)

        retry = post_qa(owner, first_body)
        retry_json = retry.json()
        check(
            "first_request_idempotent_retry",
            retry.status_code == 200 and retry_json.get("id") == first_json.get("id"),
        )
        check("retry_keeps_conversation", retry_json.get("conversation_id") == conversation_id)

        separate = post_qa(owner, {
            "question": "交班紀錄要保存多久？",
            "source": "text",
            "client_request_id": str(uuid.uuid4()),
        })
        check(
            "new_question_starts_separate_conversation",
            separate.status_code == 200
            and separate.json().get("conversation_id") != conversation_id,
        )

        follow_request = str(uuid.uuid4())
        follow_body = {
            "question": "那夜間呢？",
            "source": "text",
            "conversation_id": conversation_id,
            "client_request_id": follow_request,
        }
        follow = post_qa(owner, follow_body)
        follow_json = follow.json()
        check("explicit_continue_http_200", follow.status_code == 200, str(follow.status_code))
        check("explicit_continue_keeps_conversation", follow_json.get("conversation_id") == conversation_id)

        ended = client.post(f"/api/interactions/{conversation_id}/end", headers=owner)
        check("end_interaction_http_200", ended.status_code == 200, str(ended.status_code))
        check("interaction_has_ended_at", bool(ended.json().get("ended_at")))

        rejected = post_qa(owner, {
            **follow_body,
            "client_request_id": str(uuid.uuid4()),
        })
        check(
            "ended_interaction_rejects_new_followup",
            rejected.status_code == 409,
            str(rejected.status_code),
        )

        retry_after_end = post_qa(owner, follow_body)
        check(
            "ended_interaction_allows_same_request_retry",
            retry_after_end.status_code == 200 and retry_after_end.json().get("id") == follow_json.get("id"),
            str(retry_after_end.status_code),
        )

        for name, headers in (
            ("cross_user_blocked", peer),
            ("cross_org_blocked", other_org),
            ("role_blocked", supervisor),
        ):
            response = post_qa(headers, {
                "question": "可以繼續嗎？",
                "source": "text",
                "conversation_id": conversation_id,
                "client_request_id": str(uuid.uuid4()),
            })
            check(name, response.status_code == 404, str(response.status_code))

        forged = post_qa(owner, {
            "question": "可以繼續嗎？",
            "source": "text",
            "conversation_id": str(uuid.uuid4()),
            "client_request_id": str(uuid.uuid4()),
        })
        check("forged_conversation_blocked", forged.status_code == 404, str(forged.status_code))

        case_context = post_qa(owner, {
            "question": "一般規範問題",
            "source": "text",
            "client_request_id": str(uuid.uuid4()),
            "case_id": str(uuid.uuid4()),
            "case_context": "synthetic-only",
        })
        check(
            "case_context_rejected_by_backend",
            case_context.status_code == 422,
            str(case_context.status_code),
        )

        risk = post_qa(owner, {
            "question": "住民昏倒了沒有呼吸",
            "source": "text",
            "client_request_id": str(uuid.uuid4()),
        })
        risk_json = risk.json()
        check("high_risk_escalated", risk.status_code == 200 and risk_json.get("outcome") == "escalated")
        check("high_risk_case_created", bool(risk_json.get("case")))
        check("high_risk_has_no_citations", risk_json.get("citations") == [])

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            queued = session.scalar(select(func.count()).select_from(NotificationJob)) or 0
            mock_deliveries = session.scalar(select(func.count()).select_from(LineMockOutbox)) or 0
    finally:
        engine.dispose()
    check(
        "no_worker_or_delivery_executed",
        mock_deliveries == 0,
        f"notification_rows={queued}; mock_deliveries={mock_deliveries}; worker_not_started",
    )

    ordered = sorted(latencies_ms)
    p95_index = max(0, min(len(ordered) - 1, round(0.95 * len(ordered)) - 1))
    passed = sum(1 for item in checks if item["passed"])
    return {
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
        "latency_ms": {
            "count": len(ordered),
            "min": round(min(ordered), 2),
            "median": round(statistics.median(ordered), 2),
            "p95": round(ordered[p95_index], 2),
            "max": round(max(ordered), 2),
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = run(args.base_url, args.database_url)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
