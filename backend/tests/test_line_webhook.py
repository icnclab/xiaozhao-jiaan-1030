"""A4／A9：LINE webhook 驗簽、去重、原生語音轉錄、SSRF 防護（模擬模式）。"""

from __future__ import annotations

import json
import time
import uuid

from sqlalchemy import func, select

from app.db import new_session
from app.line.client import mock_content_path
from app.line.signature import compute_signature
from app.models import Case, LineEvent, LineMockOutbox, NotificationJob, QaItem, Transcript
from app.providers.stt import MockStt
from app.worker import drain
from tests.conftest import line_id, make_wav

SECRET = "test-channel-secret"


def event(kind: str, user: str, **kw):
    base = {
        "type": "message" if kind in {"text", "audio"} else kind,
        "mode": "active",
        "timestamp": int(time.time() * 1000),
        "source": {"type": "user", "userId": line_id(user)},
        "webhookEventId": "01TEST" + uuid.uuid4().hex[:20].upper(),
        "deliveryContext": {"isRedelivery": False},
        "replyToken": uuid.uuid4().hex,
    }
    if kind == "text":
        base["message"] = {"id": str(int(time.time() * 1e6)), "type": "text", "text": kw["text"]}
    elif kind == "audio":
        base["message"] = {"id": kw["message_id"], "type": "audio", "duration": 3000,
                           "contentProvider": kw.get("provider", {"type": "line"})}
    elif kind == "postback":
        base["postback"] = {"data": kw["data"]}
    return base


def post(client, events, secret=SECRET):
    body = json.dumps({"destination": "Utest", "events": events}, ensure_ascii=False).encode("utf-8")
    return client.post("/api/line/webhook", content=body,
                       headers={"x-line-signature": compute_signature(secret, body),
                                "content-type": "application/json"})


def outbox_texts():
    session = new_session()
    rows = session.scalars(select(LineMockOutbox).order_by(LineMockOutbox.id)).all()
    session.close()
    return [m.get("text", m.get("type")) for r in rows for m in r.messages]


def test_bad_signature_rejected(client, world):
    body = json.dumps({"events": []}).encode()
    response = client.post("/api/line/webhook", content=body, headers={"x-line-signature": "bogus"})
    assert response.status_code == 401
    # 簽章用錯的 secret 也拒絕
    assert post(client, [], secret="wrong").status_code == 401


def test_signature_checks_raw_body(client, world):
    """同一 JSON 重新排版後簽章不同 → 必須以原始 body 驗證。"""
    payload = {"destination": "U", "events": []}
    signed_body = json.dumps(payload).encode()
    other_body = json.dumps(payload, indent=2).encode()
    response = client.post("/api/line/webhook", content=other_body,
                           headers={"x-line-signature": compute_signature(SECRET, signed_body)})
    assert response.status_code == 401


def test_text_question_flow_and_redelivery_idempotent(client, world):
    """A9：同一 webhookEventId 重送不重複處理、不重複建案。"""
    ev = event("text", "cg1", text="員工停車位怎麼申請？")
    assert post(client, [ev]).json()["new"] == 1
    redelivered = dict(ev, deliveryContext={"isRedelivery": True})
    assert post(client, [redelivered]).json()["duplicate"] == 1
    drain()
    session = new_session()
    assert session.scalar(select(func.count()).select_from(LineEvent)) == 1
    assert session.scalar(select(func.count()).select_from(QaItem)) == 1
    assert session.scalar(select(func.count()).select_from(Case)) == 1
    stored = session.scalar(select(LineEvent))
    assert stored.payload_encrypted is None and stored.reply_token is None  # 處理完即清除
    session.close()
    texts = outbox_texts()
    assert any("已送交督導確認" in t for t in texts)


def test_text_answer_contains_citations(client, world):
    post(client, [event("text", "cg1", text="照護紀錄要保存多久？")])
    drain()
    texts = outbox_texts()
    assert any("AI 初步參考" in t and "出處" in t for t in texts), texts


def test_stale_reply_token_uses_push(client, world):
    ev = event("text", "cg1", text="照護紀錄要保存多久？")
    ev["timestamp"] = int((time.time() - 120) * 1000)  # 事件已兩分鐘前
    post(client, [ev])
    drain()
    session = new_session()
    kinds = [r.kind for r in session.scalars(select(LineMockOutbox))]
    assert "push" in kinds and "reply" not in kinds
    assert session.scalar(select(NotificationJob.status)) == "accepted"
    session.close()


def test_audio_message_transcribed(client, world, tmp_path):
    """A4：LINE 原生語音 → 取內容 → STT → 推播轉錄草稿 → 按「用這段提問」→ 回答。"""
    message_id = "4242424242"
    mock_content_path(message_id).write_bytes(make_wav(tmp_path / "v.wav").read_bytes())
    MockStt.script = [{"start_ms": 0, "end_ms": 1500, "text": "照護紀錄要保存多久", "uncertain": False}]
    post(client, [event("audio", "cg1", message_id=message_id)])
    drain()
    session = new_session()
    transcript = session.scalar(select(Transcript))
    from app.models import Job

    jobs_state = [(j.kind, j.status, j.last_error) for j in session.scalars(select(Job))]
    assert transcript is not None, jobs_state
    assert transcript.channel == "line" and transcript.status == "draft", (transcript.status, jobs_state)
    assert transcript.audio_path is None and transcript.audio_deleted_at is not None  # STT 後即刪原音
    session.close()
    texts = outbox_texts()
    assert any("正在轉成文字" in t for t in texts)
    assert any("語音轉文字結果" in t and "照護紀錄要保存多久" in t for t in texts), (texts, jobs_state)
    post(client, [event("postback", "cg1", data=f"action=ask_tr&t={transcript.id}")])
    drain()
    session = new_session()
    item = session.scalar(select(QaItem))
    assert item.source == "line_voice" and item.transcript_id == transcript.id
    session.close()


def test_external_content_not_downloaded(client, world):
    """SSRF：contentProvider=external 的外部連結不下載。"""
    ev = event("audio", "cg1", message_id="555",
               provider={"type": "external", "originalContentUrl": "http://169.254.169.254/latest/meta-data"})
    post(client, [ev])
    drain()
    session = new_session()
    assert session.scalar(select(func.count()).select_from(Transcript)) == 0
    assert session.scalar(select(LineEvent.error)) == "external_content_refused"
    session.close()
    assert any("不下載外部連結" in t for t in outbox_texts())


def test_unbound_user_gets_binding_link(client, world):
    ev = event("text", "stranger", text="你好")
    post(client, [ev])
    drain()
    assert any("尚未綁定" in t for t in outbox_texts())


def test_unfollow_marks_blocked_and_skips_push(client, world):
    from tests.conftest import login_web

    post(client, [dict(event("unfollow", "cg1"), replyToken=None)])
    drain()
    # 建一個案件並回覆 → 通知應為 skipped（blocked），回覆仍保存
    session = new_session()
    from app.models import User
    from app.services import cases

    cg1 = session.get(User, world.ids["cg1"])
    case, _ = cases.create_case(session, cg1, source="quick_report", summary_masked="測試", reason="測試",
                                client_request_id="req-12345678", category_id=world.ids["cat:HAPPY:其他"])
    session.commit()
    case_id = case.id
    session.close()
    headers = login_web(client, "sup_a")
    body = client.post(f"/api/admin/cases/{case_id}/reply", json={"text": "請依內規辦理", "client_request_id": "rep-12345678"},
                       headers=headers).json()
    assert body["reply_saved"] is True
    assert body["notification"]["status"] == "skipped"
    assert body["notification"]["last_error_code"] == "blocked"
