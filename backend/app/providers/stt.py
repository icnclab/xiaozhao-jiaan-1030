"""STT provider adapters。

- `whisper_http`：本機 faster-whisper sidecar（`services/stt_sidecar/server.py`），模型常駐。
- `mock`：測試用，回傳注入的片段。
- `cht`：中華電信 STT 的保留 adapter。**尚未取得官方規格與憑證，未串接**；呼叫時明確報錯，不虛構 endpoint。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.config import get_settings


class SttNotConfigured(RuntimeError):
    """STT provider 未設定或未串接。"""


@dataclass
class SttResult:
    """轉錄結果。

    Attributes:
        segments: `[{start_ms, end_ms, text, uncertain}]`，text 為未遮罩原文。
        language: 偵測語言。
        model: 使用的模型名稱。
    """

    segments: list[dict[str, Any]] = field(default_factory=list)
    language: str | None = None
    model: str | None = None


class SttProvider(Protocol):
    """STT adapter 介面。"""

    name: str

    def transcribe(self, wav_path: Path) -> SttResult:
        """轉錄 16 kHz 單聲道 wav。"""
        ...


class WhisperHttpStt:
    """呼叫本機 faster-whisper sidecar。"""

    name = "whisper_http"

    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def transcribe(self, wav_path: Path) -> SttResult:
        """見 `SttProvider.transcribe`。"""
        with wav_path.open("rb") as handle:
            response = httpx.post(
                f"{self.base_url}/transcribe",
                params={"model": self.model},
                content=handle.read(),
                headers={"Content-Type": "audio/wav"},
                timeout=self.timeout,
            )
        response.raise_for_status()
        data = response.json()
        return SttResult(segments=data["segments"], language=data.get("language"), model=data.get("model"))


class MockStt:
    """測試用 STT。`script` 可設為片段清單或例外。"""

    name = "mock"
    script: list[dict[str, Any]] | Exception | None = None

    def transcribe(self, wav_path: Path) -> SttResult:
        """見 `SttProvider.transcribe`。"""
        if isinstance(MockStt.script, Exception):
            raise MockStt.script
        segments = MockStt.script or [
            {"start_ms": 0, "end_ms": 2000, "text": "（模擬轉錄）家屬要我幫忙代購成藥可以嗎", "uncertain": False}
        ]
        return SttResult(segments=[dict(s) for s in segments], language="zh", model="mock")


class ChtStt:
    """中華電信 STT 保留 adapter（未串接）。"""

    name = "cht"

    def transcribe(self, wav_path: Path) -> SttResult:
        """見 `SttProvider.transcribe`。

        Raises:
            SttNotConfigured: 永遠拋出，直到依官方文件完成串接。
        """
        settings = get_settings()
        if not settings.cht_stt_endpoint or not settings.cht_api_key:
            raise SttNotConfigured("中華電信 STT 未設定（CHT_STT_ENDPOINT／CHT_API_KEY）")
        raise SttNotConfigured("中華電信 STT adapter 尚未依官方文件實作，未串接")


def get_stt_provider() -> SttProvider:
    """依設定建立 STT provider。"""
    settings = get_settings()
    if settings.stt_provider == "whisper_http":
        return WhisperHttpStt(settings.stt_base_url, settings.stt_model, settings.stt_timeout_sec)
    if settings.stt_provider == "mock":
        return MockStt()
    if settings.stt_provider == "cht":
        return ChtStt()
    raise RuntimeError(f"未知的 STT_PROVIDER：{settings.stt_provider}")
