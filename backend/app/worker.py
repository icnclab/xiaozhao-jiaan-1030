"""背景 worker：取工作、執行、重試；定期清理暫存資料並回報心跳。

啟動：`python -m app.worker`（可同時跑多個，靠 SKIP LOCKED 分工）。
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import time
import uuid
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import new_session
from app.line import service as line_service
from app.logging_setup import setup_logging
from app.services import documents, jobs, notifications, retention, transcripts, tts_service
from app.services import jiaan_emergency_dispatch
from app.services import jiaan_webpush

logger = logging.getLogger("worker")
SWEEP_INTERVAL_SEC = 300
EMERGENCY_SWEEP_INTERVAL_SEC = 10


class RetryLater(Exception):
    """尚未就緒，稍後重試（不是錯誤）。"""


def _doc_ingest(session: Session, payload: dict) -> None:
    documents.ingest_version(session, uuid.UUID(payload["version_id"]))
    session.commit()


def _doc_ingest_failed(session: Session, payload: dict, error: str) -> None:
    from app.models import DocumentVersion

    version = session.get(DocumentVersion, uuid.UUID(payload["version_id"]))
    if version is not None and version.status in {"uploaded", "parsing"}:
        version.status = "parse_failed"
        version.parse_error = f"解析工作失敗（{error[:80]}）"


def _stt(session: Session, payload: dict) -> None:
    transcript = transcripts.run_stt(session, uuid.UUID(payload["transcript_id"]))
    session.commit()
    if transcript.channel == "line" and transcript.status == "draft":
        line_service.notify_transcript_ready(session, transcript)
        session.commit()


def _stt_failed(session: Session, payload: dict, error: str) -> None:
    transcripts.mark_failed(session, uuid.UUID(payload["transcript_id"]), "stt_failed",
                            "轉文字失敗，可在音訊保存期限內重試；逾期請重新錄製")


def _tts(session: Session, payload: dict) -> None:
    tts_service.run_tts(session, uuid.UUID(payload["asset_id"]))
    session.commit()


def _tts_failed(session: Session, payload: dict, error: str) -> None:
    tts_service.mark_failed(session, uuid.UUID(payload["asset_id"]), error)


def _tts_push(session: Session, payload: dict) -> None:
    if not line_service.push_tts_audio(session, uuid.UUID(payload["asset_id"]), uuid.UUID(payload["user_id"])):
        raise RetryLater("tts not ready")
    session.commit()


def _notify(session: Session, payload: dict) -> None:
    ok, retryable = notifications.send(session, uuid.UUID(payload["notification_id"]))
    session.commit()
    if not ok and retryable:
        raise RetryLater("notification failed, retryable")


def _line_event(session: Session, payload: dict) -> None:
    line_service.process_event(session, uuid.UUID(payload["line_event_id"]))
    session.commit()


def _line_event_failed(session: Session, payload: dict, error: str) -> None:
    from app.models import LineEvent

    event = session.get(LineEvent, uuid.UUID(payload["line_event_id"]))
    if event is not None:
        event.status = "failed"
        event.error = error[:200]
        event.payload_encrypted = None


HANDLERS: dict[str, Callable[[Session, dict], None]] = {
    "doc_ingest": _doc_ingest,
    "stt": _stt,
    "tts": _tts,
    "tts_push": _tts_push,
    "notify": _notify,
    "line_event": _line_event,
}
FAILURE_HANDLERS: dict[str, Callable[[Session, dict, str], None]] = {
    "doc_ingest": _doc_ingest_failed,
    "stt": _stt_failed,
    "tts": _tts_failed,
    "line_event": _line_event_failed,
}


def run_one(worker_id: str, kinds: list[str] | None = None) -> bool:
    """取一筆工作執行。

    Args:
        worker_id: worker 識別。
        kinds: 限定工作種類。

    Returns:
        是否有取到工作。
    """
    session = new_session()
    try:
        job = jobs.claim(session, worker_id, kinds)
        if job is None:
            return False
        if job.attempts > job.max_attempts:
            jobs.fail(session, job, "lease expired after max attempts", retryable=False)
            _on_final_failure(job, "lease expired")
            return True
        handler = HANDLERS.get(job.kind)
        try:
            if handler is None:
                raise ValueError(f"unknown job kind {job.kind}")
            handler(session, job.payload)
            jobs.complete(session, job.id)
        except RetryLater as exc:
            session.rollback()
            if jobs.fail(session, job, str(exc)):
                _on_final_failure(job, str(exc))
        except Exception as exc:  # 工作失敗：記錄類型與摘要，不記內容
            session.rollback()
            logger.warning("job %s (%s) attempt %d failed: %s", job.id, job.kind, job.attempts, type(exc).__name__)
            if jobs.fail(session, job, f"{type(exc).__name__}: {str(exc)[:200]}"):
                _on_final_failure(job, type(exc).__name__)
        return True
    finally:
        session.close()


def _on_final_failure(job: jobs.ClaimedJob, error: str) -> None:
    handler = FAILURE_HANDLERS.get(job.kind)
    if handler is None:
        return
    session = new_session()
    try:
        handler(session, job.payload, error)
        session.commit()
    finally:
        session.close()


def drain(max_jobs: int = 100, kinds: list[str] | None = None) -> int:
    """（測試／腳本用）連續執行直到佇列沒有可執行工作。"""
    done = 0
    while done < max_jobs and run_one("drain", kinds):
        done += 1
    return done


def heartbeat(worker_id: str) -> None:
    """寫入心跳。"""
    session = new_session()
    try:
        session.execute(text(
            "INSERT INTO worker_heartbeats (worker_id, seen_at) VALUES (:w, now()) "
            "ON CONFLICT (worker_id) DO UPDATE SET seen_at = now()"), {"w": worker_id})
        session.commit()
    finally:
        session.close()


def main() -> None:
    """worker 主迴圈。"""
    setup_logging()
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    running = True

    def _stop(*_: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    logger.info("worker %s started", worker_id)
    last_sweep, last_beat, last_emergency, last_webpush = 0.0, 0.0, 0.0, 0.0
    while running:
        now = time.monotonic()
        if now - last_beat > 15:
            heartbeat(worker_id)
            last_beat = now
        if now - last_sweep > SWEEP_INTERVAL_SEC:
            session = new_session()
            try:
                retention.sweep(session)
            except Exception as exc:
                logger.warning("retention sweep failed: %s", type(exc).__name__)
            finally:
                session.close()
            last_sweep = now
        if jiaan_emergency_dispatch.is_enabled() and now - last_emergency >= EMERGENCY_SWEEP_INTERVAL_SEC:
            session = new_session()
            try:
                count = jiaan_emergency_dispatch.sweep(session)
                session.commit()
                if count:
                    logger.info("emergency notifications queued: %d", count)
            except Exception as exc:
                session.rollback()
                logger.warning("emergency sweep failed: %s", type(exc).__name__)
            finally:
                session.close()
            last_emergency = now
        # Separate web-push pipeline. Disabled by default; does not affect LINE.
        if jiaan_webpush.enabled() and now - last_webpush >= EMERGENCY_SWEEP_INTERVAL_SEC:
            session = new_session()
            try:
                staged = jiaan_webpush.sweep(session)
                session.commit()
                sent = jiaan_webpush.dispatch_due(session)
                session.commit()
                if staged or sent:
                    logger.info('webpush staged=%d attempted=%d', staged, sent)
            except Exception as exc:
                session.rollback()
                logger.warning('webpush cycle failed: %s', type(exc).__name__)
            finally:
                session.close()
            last_webpush = now
        try:
            worked = run_one(worker_id)
        except Exception as exc:  # 資料庫暫時不可用等
            logger.warning("worker loop error: %s", type(exc).__name__)
            worked = False
            time.sleep(2)
        if not worked:
            time.sleep(0.5)
    logger.info("worker %s stopped", worker_id)


if __name__ == "__main__":
    main()
