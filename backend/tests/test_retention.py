"""A12：暫存音訊與未遮罩草稿到期清除；敏感文字與 token 不進一般日誌與稽核。"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select, text

from app.db import new_session
from app.logging_setup import RedactingFilter
from app.models import AuditLog, Transcript
from app.providers.stt import MockStt
from app.services import retention
from app.services.jobs import utcnow
from app.worker import drain
from tests.conftest import login_liff, make_wav, new_id

SECRET_PHRASE = "王大明先生住在三零二房"


def upload(client, headers, path):
    with path.open("rb") as handle:
        return client.post("/api/audio/uploads", headers=headers,
                           data={"mode": "conversation", "client_upload_id": new_id(), "consent_confirmed": "true"},
                           files={"file": ("rec.wav", handle, "audio/wav")}).json()


def test_expired_audio_deleted_and_retry_requires_rerecord(client, world, tmp_path):
    headers = login_liff(client, "cg1")
    transcript_id = upload(client, headers, make_wav(tmp_path / "a.wav"))["transcript_id"]
    session = new_session()
    transcript = session.get(Transcript, transcript_id)
    audio_path = Path(transcript.audio_path)
    assert audio_path.exists()
    # 模擬 worker 中斷：工作沒跑，音訊到期
    transcript.audio_expires_at = utcnow() - timedelta(minutes=1)
    session.commit()
    counts = retention.sweep(session)
    session.close()
    assert counts["audio"] == 1 and not audio_path.exists()
    data = client.get(f"/api/transcripts/{transcript_id}", headers=headers).json()
    assert data["status"] == "expired" and data["error_code"] == "audio_expired"
    retry = client.post(f"/api/transcripts/{transcript_id}/retry", headers=headers)
    assert retry.status_code == 410 and "重新錄製" in retry.json()["error"]["message"]
    # 殘留的 STT 工作執行時也不會假裝成功
    drain()
    assert client.get(f"/api/transcripts/{transcript_id}", headers=headers).json()["status"] == "expired"


def test_expired_draft_purged(client, world, tmp_path):
    headers = login_liff(client, "cg1")
    MockStt.script = [{"start_ms": 0, "end_ms": 1000, "text": SECRET_PHRASE, "uncertain": False}]
    transcript_id = upload(client, headers, make_wav(tmp_path / "a.wav"))["transcript_id"]
    drain()
    session = new_session()
    transcript = session.get(Transcript, transcript_id)
    assert transcript.draft_encrypted is not None
    assert SECRET_PHRASE.encode("utf-8") not in transcript.draft_encrypted  # 草稿是加密的
    transcript.draft_expires_at = utcnow() - timedelta(minutes=1)
    session.commit()
    retention.sweep(session)
    session.refresh(transcript)
    assert transcript.draft_encrypted is None and transcript.status == "expired"
    session.close()


def test_sensitive_text_not_in_logs_or_audit(client, world, tmp_path, caplog):
    headers = login_liff(client, "cg1")
    MockStt.script = [{"start_ms": 0, "end_ms": 1000, "text": SECRET_PHRASE, "uncertain": False}]
    with caplog.at_level(logging.DEBUG):
        client.post("/api/qa/ask", headers=headers, json={"question": SECRET_PHRASE + "要代購成藥可以嗎",
                                                          "client_request_id": new_id()})
        upload(client, headers, make_wav(tmp_path / "a.wav"))
        drain()
    assert SECRET_PHRASE not in caplog.text and "王大明" not in caplog.text
    session = new_session()
    dump = " ".join(str(r.meta) for r in session.scalars(select(AuditLog)))
    assert "王大明" not in dump
    # 資料庫裡的問答與事件表不存未遮罩姓名
    leaked = session.execute(text(
        "SELECT count(*) FROM qa_items WHERE question_masked LIKE '%王大明%'")).scalar()
    assert leaked == 0
    session.close()


def test_redacting_filter_masks_tokens():
    record = logging.LogRecord("x", logging.INFO, __file__, 1,
                               "auth Bearer abcdefghijklmnopqrstuvwxyz0123 secret=supersecretvalue done", (), None)
    RedactingFilter().filter(record)
    assert "abcdefghijklmnopqrstuvwxyz0123" not in record.msg and "supersecretvalue" not in record.msg


def test_audit_log_is_append_only(world):
    session = new_session()
    session.execute(text("INSERT INTO audit_logs (action, outcome, meta, created_at) VALUES ('t','ok','{}', now())"))
    session.commit()
    try:
        session.execute(text("UPDATE audit_logs SET action = 'tampered'"))
        session.commit()
        raise AssertionError("audit log should be append-only")
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        assert "append-only" in str(exc)
    finally:
        session.close()
