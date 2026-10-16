"""音訊工具：以 ffprobe 實際解碼驗證、轉 16 kHz 單聲道 wav、轉 m4a。

格式檢查一律看解碼結果，不看副檔名或前端宣告的 MIME。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class AudioError(Exception):
    """音訊無法解碼或不符限制。

    Attributes:
        code: 機器可讀錯誤碼（decode_failed、too_long、too_short、no_audio）。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AudioInfo:
    """解碼驗證結果。"""

    duration_ms: int
    codec: str
    format_name: str


def _bin(name: str) -> str:
    from app.config import get_settings

    ffmpeg_dir = get_settings().ffmpeg_dir
    if ffmpeg_dir:
        candidate = Path(ffmpeg_dir) / (name + (".exe" if os.name == "nt" else ""))
        if candidate.exists():
            return str(candidate)
    path = shutil.which(name)
    if not path:
        raise AudioError("tool_missing", f"找不到 {name}，請安裝 ffmpeg")
    return path


def _run(args: list[str], timeout: float = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )


def probe(path: Path) -> AudioInfo:
    """用 ffprobe 讀取音訊串流資訊，並實際解碼整個檔案確認可用。

    Args:
        path: 音訊檔路徑。

    Returns:
        音訊資訊。

    Raises:
        AudioError: 無法解碼或沒有音訊串流。
    """
    result = _run(
        [
            _bin("ffprobe"), "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name:format=format_name,duration",
            "-of", "json", str(path),
        ]
    )
    if result.returncode != 0:
        raise AudioError("decode_failed", "無法辨識的音訊格式")
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise AudioError("no_audio", "檔案中沒有音訊")
    # 實際解碼到 null muxer，並由解碼結果計算長度（瀏覽器錄的 webm 常缺 duration 欄位）
    decode = _run([_bin("ffmpeg"), "-v", "error", "-i", str(path), "-f", "null", "-"], timeout=300)
    if decode.returncode != 0 or "Invalid data" in decode.stderr:
        raise AudioError("decode_failed", "音訊解碼失敗，檔案可能損毀")
    duration_text = (data.get("format") or {}).get("duration")
    duration_ms = int(float(duration_text) * 1000) if duration_text not in (None, "N/A") else 0
    if duration_ms <= 0:
        duration_ms = _decoded_duration_ms(path)
    return AudioInfo(
        duration_ms=duration_ms,
        codec=streams[0].get("codec_name", "unknown"),
        format_name=(data.get("format") or {}).get("format_name", "unknown"),
    )


def _decoded_duration_ms(path: Path) -> int:
    """以解碼後的 PCM 樣本數計算長度（用於缺 duration 的串流格式）。"""
    result = subprocess.run(
        [_bin("ffmpeg"), "-v", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise AudioError("decode_failed", "音訊解碼失敗")
    return int(len(result.stdout) / 2 / 16000 * 1000)


def to_wav16k(src: Path, dst: Path) -> Path:
    """轉成 16 kHz 單聲道 PCM wav（STT 輸入）。

    Args:
        src: 來源音訊。
        dst: 輸出 wav 路徑。

    Returns:
        輸出路徑。

    Raises:
        AudioError: 轉檔失敗。
    """
    result = _run(
        [_bin("ffmpeg"), "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(dst)]
    )
    if result.returncode != 0:
        raise AudioError("decode_failed", "音訊轉檔失敗")
    return dst


def to_m4a(src: Path, dst: Path) -> Path:
    """轉成 AAC m4a（LINE 音訊訊息與瀏覽器播放皆支援）。

    Args:
        src: 來源音訊（通常是 TTS 產生的 wav）。
        dst: 輸出路徑。

    Returns:
        輸出路徑。
    """
    result = _run(
        [_bin("ffmpeg"), "-v", "error", "-y", "-i", str(src), "-c:a", "aac", "-b:a", "64k",
         "-movflags", "+faststart", str(dst)]
    )
    if result.returncode != 0:
        raise AudioError("encode_failed", "音訊編碼失敗")
    return dst
