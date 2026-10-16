"""資料保留與清除：暫存音訊、未遮罩草稿、TTS 檔、事件內容、過期 session。

成功、失敗、工作中斷三種情況都靠「到期時間」兜底：就算 worker 在 STT 中途當掉，
音訊到期後也會被這裡刪除，對應紀錄標為 expired，使用者重試時會被要求重新錄製。
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.line.service import cleanup_payloads
from app.models import BindingCode, Transcript, TtsAsset
from app.services import jobs
from app.services.transcripts import delete_audio

logger = logging.getLogger(__name__)


def sweep(session: Session) -> dict[str, int]:
    """執行一次清理（由 worker 定期呼叫）。

    Args:
        session: ORM session（本函式會 commit）。

    Returns:
        各類清除筆數（只含數量）。
    """
    now = jobs.utcnow()
    counts = {"audio": 0, "drafts": 0, "tts": 0, "events": 0, "sessions": 0, "orphan_files": 0}

    expired_audio = session.scalars(
        select(Transcript).where(Transcript.audio_path.is_not(None), Transcript.audio_expires_at < now)
    ).all()
    for transcript in expired_audio:
        delete_audio(transcript)
        counts["audio"] += 1
        if transcript.status in {"queued", "transcribing", "failed", "uploaded"}:
            transcript.status = "expired"
            transcript.error_code = "audio_expired"
            transcript.error_message = "音訊已依規定清除，請重新錄製"

    expired_drafts = session.scalars(
        select(Transcript).where(Transcript.draft_encrypted.is_not(None), Transcript.draft_expires_at < now)
    ).all()
    for transcript in expired_drafts:
        transcript.draft_encrypted = None
        transcript.draft_deleted_at = now
        if transcript.status == "draft":
            transcript.status = "expired"
            transcript.error_code = "draft_expired"
            transcript.error_message = "逐字稿草稿逾時未確認，已清除"
        counts["drafts"] += 1

    for asset in session.scalars(
        select(TtsAsset).where(TtsAsset.status == "ready", TtsAsset.expires_at < now)
    ).all():
        if asset.file_path:
            Path(asset.file_path).unlink(missing_ok=True)
        asset.file_path = None
        asset.status = "expired"
        counts["tts"] += 1

    counts["events"] = cleanup_payloads(session)
    result = session.execute(
        text("DELETE FROM sessions WHERE expires_at < now() - interval '1 day' OR revoked_at IS NOT NULL")
    )
    counts["sessions"] = result.rowcount or 0
    session.query(BindingCode).filter(
        or_(BindingCode.expires_at < now, BindingCode.used_at.is_not(None))
    ).delete(synchronize_session=False)

    # 目錄中找不到對應紀錄的暫存音訊（例如上傳中斷）：超過 TTL 就刪
    audio_dir = get_settings().data_dir / "audio_tmp"
    if audio_dir.exists():
        ttl = get_settings().audio_ttl_min * 60
        known = {Path(p).name for p in session.scalars(
            select(Transcript.audio_path).where(Transcript.audio_path.is_not(None))) if p}
        for path in audio_dir.iterdir():
            if path.name not in known and (now.timestamp() - path.stat().st_mtime) > ttl:
                path.unlink(missing_ok=True)
                counts["orphan_files"] += 1
    mock_dir = get_settings().data_dir / "mock_line_content"
    if mock_dir.exists():
        for path in mock_dir.iterdir():
            if (now.timestamp() - path.stat().st_mtime) > get_settings().audio_ttl_min * 60:
                path.unlink(missing_ok=True)
                counts["orphan_files"] += 1
    session.commit()
    if any(counts.values()):
        logger.info("retention sweep %s", counts)
    return counts
