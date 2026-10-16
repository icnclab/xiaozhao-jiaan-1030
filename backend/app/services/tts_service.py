"""回答語音（TTS）：使用者點選才產生；失敗不影響文字回答與案件。"""

from __future__ import annotations

import time
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Citation, Chunk, Document, DocumentVersion, QaItem, TtsAsset, User
from app.providers.tts import get_tts_provider
from app.security import new_token, sign_media_token
from app.services import audit, jobs
from app.services.audio import probe, to_m4a


def _tts_dir() -> Path:
    folder = get_settings().data_dir / "tts"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def speech_text(session: Session, item: QaItem) -> str:
    """組出要唸的文字：回答＋出處（文件名與條號），不唸網址。"""
    text = item.answer_text or ""
    if item.outcome == "answered":
        rows = session.execute(
            select(Document.title, Chunk.locator)
            .select_from(Citation)
            .join(Chunk, Chunk.id == Citation.chunk_id)
            .join(DocumentVersion, DocumentVersion.id == Citation.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Citation.qa_item_id == item.id)
            .order_by(Citation.rank)
        ).all()
        sources = "；".join(f"出處{i}，{r.title}，{r.locator.split('｜')[0]}" for i, r in enumerate(rows, 1))
        text = text.replace("（出處", "（出處 ").strip()
        if sources:
            text += f"。{sources}。這是 AI 初步參考，實際做法請依督導確認。"
    return text


def request_tts(session: Session, user: User, item: QaItem) -> TtsAsset:
    """建立（或取得既有的）TTS 工作。同一回答只會有一筆。"""
    asset = session.scalar(select(TtsAsset).where(TtsAsset.qa_item_id == item.id))
    if asset and asset.status in {"queued", "running", "ready"}:
        if asset.status != "ready" or (asset.expires_at and asset.expires_at > jobs.utcnow()):
            return asset
    if asset is None:
        asset = TtsAsset(qa_item_id=item.id, status="queued", provider=get_settings().tts_provider,
                         token_id=new_token(24))
        session.add(asset)
    else:  # 失敗或過期：重新產生，換新 token
        asset.status = "queued"
        asset.error = None
        asset.token_id = new_token(24)
    session.flush()
    jobs.enqueue(session, "tts", {"asset_id": str(asset.id)}, f"tts:{asset.id}:{asset.token_id[:8]}", max_attempts=2)
    audit.record(session, "tts.request", actor=user, target_type="qa_item", target_id=item.id)
    session.commit()
    return asset


def run_tts(session: Session, asset_id: uuid.UUID) -> TtsAsset:
    """產生語音檔（由 worker 呼叫）。"""
    asset = session.get(TtsAsset, asset_id)
    if asset is None:
        raise ValueError("tts asset not found")
    if asset.status == "ready":
        return asset
    item = session.get(QaItem, asset.qa_item_id)
    assert item is not None
    asset.status = "running"
    session.commit()
    provider = get_tts_provider()
    folder = _tts_dir()
    wav = folder / f"{asset.id}.wav"
    m4a = folder / f"{asset.id}.m4a"
    started = time.perf_counter()
    try:
        provider.synthesize(speech_text(session, item), wav)
        to_m4a(wav, m4a)
        info = probe(m4a)
    finally:
        wav.unlink(missing_ok=True)
    asset.file_path = str(m4a)
    asset.mime = "audio/mp4"
    asset.duration_ms = info.duration_ms
    asset.provider = provider.name
    asset.tts_ms = int((time.perf_counter() - started) * 1000)
    asset.expires_at = jobs.utcnow() + timedelta(hours=get_settings().tts_ttl_hours)
    asset.status = "ready"
    return asset


def mark_failed(session: Session, asset_id: uuid.UUID, error: str) -> None:
    """TTS 最終失敗。"""
    asset = session.get(TtsAsset, asset_id)
    if asset is not None and asset.status != "ready":
        asset.status = "failed"
        asset.error = error[:300]


def media_url(asset: TtsAsset) -> str | None:
    """限時簽章播放 URL（不可枚舉）。"""
    if asset.status != "ready" or asset.expires_at is None:
        return None
    token = sign_media_token(asset.token_id, int(asset.expires_at.timestamp()))
    return f"{get_settings().public_base_url.rstrip('/')}/api/media/tts/{token}"
