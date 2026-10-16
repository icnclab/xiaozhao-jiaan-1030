"""語音上傳與轉錄。

流程：驗證身分與授權 → 接收音訊（冪等）→ ffprobe 實際解碼驗證 → STT →（可選）說話者分段
→ 未遮罩草稿加密暫存 → 使用者修正與角色確認 → 保存去識別化版本與修訂軌跡 → 清除暫存。

原則：
- 原始音訊只在 STT 所需期間暫存；STT 成功立即刪除；失敗或中斷則到期由清理工作刪除。
- 音訊已刪除的失敗工作，重試時明確要求重新錄製，不假裝仍可重試。
- 說話者只標 speaker_N 或 unknown；角色（長輩、家屬、照服員）由照服員確認，不以聲音推測。
"""

from __future__ import annotations

import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Transcript, TranscriptRevision, TranscriptSegment, User
from app.providers.diarization import UNKNOWN_SPEAKER, get_diarization_provider
from app.providers.stt import get_stt_provider
from app.security import decrypt_json, encrypt_json
from app.services import audit, jobs
from app.services.audio import AudioError, probe, to_wav16k
from app.services.deid import deidentify

CONSENT_TEXT_VERSION = "2026-09-11.1"
CONSENT_TEXT = (
    "錄音只用於把現場談話轉成文字，協助您查詢規範或送交督導確認。"
    "開始前請告知在場的長輩、家屬與同仁，並取得同意；不同意就不要錄。"
    "原始錄音在轉成文字後即刪除，未確認的逐字稿最多暫存 24 小時。"
    "（本同意確認為 MVP 流程，機構正式同意書另依機構規定辦理。）"
)
ROLES = {"caregiver": "照服員", "resident": "長輩", "family": "家屬", "staff": "其他工作人員", "unknown": "未辨識"}
MODES = {"question", "conversation"}


class TranscriptError(Exception):
    """轉錄操作錯誤。"""

    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def _audio_dir() -> Path:
    folder = get_settings().data_dir / "audio_tmp"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _limit_sec(mode: str) -> int:
    settings = get_settings()
    return settings.question_max_sec if mode == "question" else settings.conversation_max_sec


def create_upload(
    session: Session,
    user: User,
    *,
    data: bytes,
    mode: str,
    client_upload_id: str,
    consent_confirmed: bool,
    channel: str = "liff",
    line_message_id: str | None = None,
    client_mime: str | None = None,
) -> tuple[Transcript, bool]:
    """接收音訊並排入轉錄；同一 client_upload_id（或 LINE 訊息 ID）重送回傳同一筆。

    Args:
        session: ORM session（本函式會 commit）。
        user: 上傳者。
        data: 音訊位元組。
        mode: question 或 conversation。
        client_upload_id: 冪等鍵。
        consent_confirmed: 是否已確認告知同意（conversation 必須為 True）。
        channel: liff 或 line。
        line_message_id: LINE 訊息 ID。
        client_mime: 前端宣告的 MIME（只作紀錄，不作格式判斷）。

    Returns:
        (轉錄紀錄, 是否新建)。

    Raises:
        TranscriptError: 驗證失敗。
    """
    settings = get_settings()
    if mode not in MODES:
        raise TranscriptError("invalid_mode", "模式不正確")
    existing = session.scalar(
        select(Transcript).where(Transcript.user_id == user.id, Transcript.client_upload_id == client_upload_id)
    )
    if existing:
        return existing, False
    if mode == "conversation" and not consent_confirmed:
        raise TranscriptError("consent_required", "談話錄音須先確認已告知在場者並取得同意")
    if not data:
        raise TranscriptError("empty", "沒有收到音訊")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise TranscriptError("too_large", f"音訊超過 {settings.max_upload_mb} MB", 413)

    transcript_id = uuid.uuid4()
    path = _audio_dir() / f"{transcript_id}.bin"
    path.write_bytes(data)
    try:
        info = probe(path)
    except AudioError as exc:
        path.unlink(missing_ok=True)
        raise TranscriptError(exc.code, str(exc), 422) from exc
    limit = _limit_sec(mode)
    if info.duration_ms > limit * 1000 + 500:
        path.unlink(missing_ok=True)
        raise TranscriptError("too_long", f"音訊長度超過 {limit} 秒上限", 413)
    if info.duration_ms < 300:
        path.unlink(missing_ok=True)
        raise TranscriptError("too_short", "錄音太短，請再錄一次", 422)

    now = jobs.utcnow()
    transcript = Transcript(
        id=transcript_id,
        org_id=user.org_id,
        user_id=user.id,
        mode=mode,
        channel=channel,
        client_upload_id=client_upload_id,
        line_message_id=line_message_id,
        status="queued",
        consent_confirmed_at=now if consent_confirmed else None,
        consent_text_version=CONSENT_TEXT_VERSION if consent_confirmed else None,
        audio_path=str(path),
        audio_mime=f"{info.format_name}/{info.codec}" + (f" (client:{client_mime[:40]})" if client_mime else ""),
        audio_duration_ms=info.duration_ms,
        audio_size=len(data),
        audio_expires_at=now + timedelta(minutes=settings.audio_ttl_min),
        speaker_roles={},
    )
    session.add(transcript)
    session.flush()
    jobs.enqueue(session, "stt", {"transcript_id": str(transcript_id)}, f"stt:{transcript_id}:0", max_attempts=3)
    audit.record(session, "audio.upload", actor=user, target_type="transcript", target_id=transcript_id,
                 meta={"mode": mode, "channel": channel, "duration_ms": info.duration_ms, "bytes": len(data)})
    session.commit()
    return transcript, True


def delete_audio(transcript: Transcript) -> None:
    """刪除暫存音訊並記錄時間。"""
    if transcript.audio_path:
        Path(transcript.audio_path).unlink(missing_ok=True)
    transcript.audio_path = None
    if transcript.audio_deleted_at is None:
        transcript.audio_deleted_at = jobs.utcnow()


def run_stt(session: Session, transcript_id: uuid.UUID) -> Transcript:
    """執行轉錄（由 worker 呼叫）。失敗時拋例外讓工作佇列重試。

    Args:
        session: ORM session（由呼叫端 commit）。
        transcript_id: 轉錄 ID。

    Returns:
        更新後的轉錄。
    """
    settings = get_settings()
    transcript = session.get(Transcript, transcript_id)
    if transcript is None:
        raise TranscriptError("not_found", "轉錄不存在")
    if transcript.status in {"draft", "confirmed", "expired", "cancelled"}:
        return transcript  # 冪等
    audio_path = Path(transcript.audio_path) if transcript.audio_path else None
    if audio_path is None or not audio_path.exists() or (
        transcript.audio_expires_at and transcript.audio_expires_at < jobs.utcnow()
    ):
        delete_audio(transcript)
        transcript.status = "expired"
        transcript.error_code = "audio_expired"
        transcript.error_message = "音訊已依規定清除，請重新錄製"
        return transcript
    transcript.status = "transcribing"
    transcript.attempts += 1
    session.flush()
    session.commit()

    wav_path = audio_path.with_suffix(".wav")
    started = time.perf_counter()
    try:
        to_wav16k(audio_path, wav_path)
        result = get_stt_provider().transcribe(wav_path)
        speakers = get_diarization_provider().label(wav_path, result.segments)
    finally:
        wav_path.unlink(missing_ok=True)
    segments: list[dict[str, Any]] = []
    for index, (segment, speaker) in enumerate(zip(result.segments, speakers, strict=True)):
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        segments.append({
            "idx": index,
            "start_ms": int(segment.get("start_ms", 0)),
            "end_ms": int(segment.get("end_ms", 0)),
            "speaker": speaker or UNKNOWN_SPEAKER,
            "text": text,
            "uncertain": bool(segment.get("uncertain", False)),
        })
    transcript.stt_ms = int((time.perf_counter() - started) * 1000)
    transcript.stt_provider = get_stt_provider().name
    transcript.stt_model = result.model
    transcript.draft_encrypted = encrypt_json({"segments": segments, "language": result.language})
    transcript.draft_expires_at = jobs.utcnow() + timedelta(hours=settings.draft_ttl_hours)
    transcript.draft_ready_at = jobs.utcnow()
    transcript.status = "draft" if segments else "failed"
    if not segments:
        transcript.error_code = "no_speech"
        transcript.error_message = "沒有辨識到語音內容，請靠近一點再錄一次"
    delete_audio(transcript)  # STT 完成即刪除原音
    return transcript


def mark_failed(session: Session, transcript_id: uuid.UUID, error_code: str, message: str) -> None:
    """工作最終失敗時更新狀態（音訊保留到到期，供手動重試）。"""
    transcript = session.get(Transcript, transcript_id)
    if transcript is None or transcript.status in {"draft", "confirmed", "expired", "cancelled"}:
        return
    transcript.status = "failed"
    transcript.error_code = error_code
    transcript.error_message = message


def retry(session: Session, user: User, transcript: Transcript) -> Transcript:
    """手動重試；音訊已刪除則回 410 並要求重新錄製。"""
    if transcript.status not in {"failed", "expired"}:
        raise TranscriptError("invalid_state", "此紀錄目前不需要重試", 409)
    if transcript.audio_path is None or not Path(transcript.audio_path).exists() or (
        transcript.audio_expires_at and transcript.audio_expires_at < jobs.utcnow()
    ):
        delete_audio(transcript)
        transcript.status = "expired"
        transcript.error_code = "audio_expired"
        transcript.error_message = "音訊已依規定清除，請重新錄製"
        session.commit()
        raise TranscriptError("audio_expired", "音訊已依規定清除，請重新錄製", 410)
    transcript.status = "queued"
    transcript.error_code = None
    transcript.error_message = None
    jobs.enqueue(session, "stt", {"transcript_id": str(transcript.id)},
                 f"stt:{transcript.id}:{transcript.attempts}", max_attempts=3)
    audit.record(session, "audio.retry", actor=user, target_type="transcript", target_id=transcript.id)
    session.commit()
    return transcript


def read_draft(transcript: Transcript) -> list[dict[str, Any]]:
    """解密未遮罩草稿（只給本人）。"""
    if transcript.draft_encrypted is None:
        return []
    return decrypt_json(transcript.draft_encrypted)["segments"]


def confirm(
    session: Session,
    user: User,
    transcript: Transcript,
    *,
    edits: list[dict[str, Any]],
    roles: dict[str, str],
    selected_idx: list[int],
    summary: str | None,
) -> Transcript:
    """確認轉錄：套用修正、角色映射，保存遮罩版與修訂軌跡，刪除未遮罩草稿。

    Args:
        session: ORM session（本函式會 commit）。
        user: 本人。
        transcript: 轉錄。
        edits: `[{idx, text, speaker, uncertain?}]`，未列出的片段維持原樣。
        roles: speaker 標籤 → 角色（caregiver、resident、family、staff、unknown）。
        selected_idx: 使用者選取要拿去查詢或送交的片段。
        summary: 使用者確認的摘要（可空）。

    Returns:
        已確認的轉錄。
    """
    if transcript.status != "draft":
        raise TranscriptError("invalid_state", "只有待確認的草稿可以確認", 409)
    if transcript.draft_expires_at and transcript.draft_expires_at < jobs.utcnow():
        raise TranscriptError("draft_expired", "逐字稿草稿已逾時清除，請重新錄製", 410)
    draft = {seg["idx"]: seg for seg in read_draft(transcript)}
    edit_map = {int(e["idx"]): e for e in edits}
    unknown_idx = set(edit_map) - set(draft)
    if unknown_idx:
        raise TranscriptError("invalid_segment", "修正的片段不存在")
    valid_speakers = {f"speaker_{n}" for n in range(1, 9)} | {UNKNOWN_SPEAKER}
    clean_roles: dict[str, str] = {}
    for speaker, role in roles.items():
        if speaker not in valid_speakers or role not in ROLES:
            raise TranscriptError("invalid_role", "角色標註不正確")
        if speaker != UNKNOWN_SPEAKER:
            clean_roles[speaker] = role
    session.query(TranscriptSegment).filter(TranscriptSegment.transcript_id == transcript.id).delete()
    selected = set(selected_idx)
    for idx, seg in sorted(draft.items()):
        edit = edit_map.get(idx, {})
        new_text = str(edit.get("text", seg["text"])).strip()
        new_speaker = str(edit.get("speaker", seg["speaker"]))
        if new_speaker not in valid_speakers:
            raise TranscriptError("invalid_role", "說話者標記不正確")
        masked_before = deidentify(seg["text"]).text
        masked_after = deidentify(new_text).text
        edited = new_text != seg["text"]
        if edited or new_speaker != seg["speaker"]:
            session.add(TranscriptRevision(transcript_id=transcript.id, idx=idx, before_masked=masked_before,
                                           after_masked=masked_after, speaker_before=seg["speaker"],
                                           speaker_after=new_speaker, revised_by=user.id))
        if not masked_after:
            continue
        session.add(TranscriptSegment(
            transcript_id=transcript.id, idx=idx, start_ms=seg["start_ms"], end_ms=seg["end_ms"],
            speaker=new_speaker, text_masked=masked_after,
            uncertain=bool(edit.get("uncertain", seg["uncertain"])), edited=edited, selected=idx in selected,
        ))
    transcript.speaker_roles = clean_roles
    transcript.summary_masked = deidentify(summary.strip()).text if summary and summary.strip() else None
    transcript.draft_encrypted = None
    transcript.draft_deleted_at = jobs.utcnow()
    transcript.status = "confirmed"
    transcript.confirmed_at = jobs.utcnow()
    audit.record(session, "transcript.confirm", actor=user, target_type="transcript", target_id=transcript.id,
                 meta={"segments": len(draft), "edited": sum(1 for e in edit_map.values() if "text" in e),
                       "roles_assigned": len(clean_roles), "selected": len(selected)})
    session.commit()
    return transcript


def cancel(session: Session, user: User, transcript: Transcript) -> None:
    """取消：立即刪除音訊與草稿。"""
    delete_audio(transcript)
    transcript.draft_encrypted = None
    if transcript.draft_deleted_at is None and transcript.draft_ready_at is not None:
        transcript.draft_deleted_at = jobs.utcnow()
    if transcript.status != "confirmed":
        transcript.status = "cancelled"
    audit.record(session, "transcript.cancel", actor=user, target_type="transcript", target_id=transcript.id)
    session.commit()
