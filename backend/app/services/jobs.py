"""PostgreSQL 背景工作佇列。

- 排入：`idempotency_key` 唯一，重複排入不會產生第二筆。
- 取工作：`FOR UPDATE SKIP LOCKED`＋租約（lease）；worker 當掉時租約逾時，其他 worker 可接手。
- 失敗：指數退避重試，超過上限標 dead，呼叫端依工作種類把業務狀態標為失敗。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Job

LEASE_SECONDS = {"stt": 900, "doc_ingest": 600, "tts": 300}
DEFAULT_LEASE = 120


def utcnow() -> datetime:
    """目前 UTC 時間（含時區）。"""
    return datetime.now(timezone.utc)


def enqueue(
    session: Session,
    kind: str,
    payload: dict[str, Any],
    idempotency_key: str,
    *,
    delay_sec: float = 0,
    max_attempts: int = 5,
) -> None:
    """排入工作；同一冪等鍵已存在時不動作。

    Args:
        session: ORM session（由呼叫端 commit，確保與業務資料同一交易）。
        kind: 工作種類。
        payload: 參數（只放 ID，不放敏感文字）。
        idempotency_key: 冪等鍵。
        delay_sec: 延後秒數。
        max_attempts: 最大嘗試次數。
    """
    statement = (
        insert(Job)
        .values(
            id=uuid.uuid4(),
            kind=kind,
            payload=payload,
            status="queued",
            attempts=0,
            max_attempts=max_attempts,
            # 用資料庫時間：API 主機與 DB 容器的時鐘若有偏差，Python 時間可能「在未來」而永遠不被取走
            run_after=func.now() + timedelta(seconds=delay_sec),
            idempotency_key=idempotency_key,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    session.execute(statement)


@dataclass(frozen=True)
class ClaimedJob:
    """取得的工作。"""

    id: uuid.UUID
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


def claim(session: Session, worker_id: str, kinds: list[str] | None = None) -> ClaimedJob | None:
    """取一筆可執行的工作並設定租約（含逾時租約回收）。

    Args:
        session: ORM session（本函式會 commit）。
        worker_id: worker 識別。
        kinds: 限定工作種類；None 表示全部。

    Returns:
        取得的工作或 None。
    """
    kind_filter = "AND kind = ANY(:kinds)" if kinds else ""
    row = session.execute(
        text(
            f"""
            UPDATE jobs SET status = 'running', attempts = attempts + 1, locked_by = :worker,
                   lease_until = now() + make_interval(secs => CASE kind
                        WHEN 'stt' THEN :lease_stt WHEN 'doc_ingest' THEN :lease_doc
                        WHEN 'tts' THEN :lease_tts ELSE :lease_default END),
                   updated_at = now()
            WHERE id = (
                SELECT id FROM jobs
                WHERE ((status = 'queued' AND run_after <= now())
                       OR (status = 'running' AND lease_until < now()))
                  {kind_filter}
                ORDER BY run_after
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, kind, payload, attempts, max_attempts
            """
        ),
        {
            "worker": worker_id,
            "kinds": kinds,
            "lease_stt": LEASE_SECONDS["stt"],
            "lease_doc": LEASE_SECONDS["doc_ingest"],
            "lease_tts": LEASE_SECONDS["tts"],
            "lease_default": DEFAULT_LEASE,
        },
    ).first()
    session.commit()
    if row is None:
        return None
    return ClaimedJob(id=row.id, kind=row.kind, payload=row.payload, attempts=row.attempts,
                      max_attempts=row.max_attempts)


def complete(session: Session, job_id: uuid.UUID) -> None:
    """標記完成。"""
    session.execute(
        text("UPDATE jobs SET status='done', finished_at=now(), lease_until=NULL, updated_at=now() WHERE id=:id"),
        {"id": job_id},
    )
    session.commit()


def fail(session: Session, job: ClaimedJob, error: str, *, retryable: bool = True) -> bool:
    """記錄失敗；可重試且未達上限時排回佇列。

    Args:
        session: ORM session（本函式會 commit）。
        job: 工作。
        error: 錯誤摘要（不可含敏感內容）。
        retryable: 是否可重試。

    Returns:
        True 表示已成為最終失敗（dead），呼叫端應更新業務狀態。
    """
    final = (not retryable) or job.attempts >= job.max_attempts
    backoff = min(2 ** job.attempts * 5, 600)
    session.execute(
        text(
            """
            UPDATE jobs SET status = :status, last_error = :error, lease_until = NULL,
                   run_after = now() + make_interval(secs => :backoff), updated_at = now(),
                   finished_at = CASE WHEN :final THEN now() ELSE NULL END
            WHERE id = :id
            """
        ),
        {"status": "dead" if final else "queued", "error": error[:500], "backoff": backoff,
         "final": final, "id": job.id},
    )
    session.commit()
    return final
