"""說話者分段 adapter。

目前只提供 `none`：所有片段標為 `unknown`（畫面顯示「未辨識」），由照服員手動指定
speaker_1、speaker_2… 與角色。本機沒有經驗證的 diarization 模型，
**不以聲音猜測誰是長輩、家屬或照服員**。日後接入模型時，只能輸出 speaker_N 標籤，角色仍由人確認。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from app.config import get_settings

UNKNOWN_SPEAKER = "unknown"


class DiarizationProvider(Protocol):
    """說話者分段介面。"""

    name: str

    def label(self, wav_path: Path, segments: list[dict[str, Any]]) -> list[str]:
        """為每個片段回傳 speaker 標籤（speaker_N 或 unknown）。"""
        ...


class NoDiarization:
    """不分段：全部未辨識。"""

    name = "none"

    def label(self, wav_path: Path, segments: list[dict[str, Any]]) -> list[str]:
        """見 `DiarizationProvider.label`。"""
        return [UNKNOWN_SPEAKER for _ in segments]


def get_diarization_provider() -> DiarizationProvider:
    """依設定建立說話者分段 provider。"""
    name = get_settings().diarization_provider
    if name == "none":
        return NoDiarization()
    raise RuntimeError(f"未知或未實作的 DIARIZATION_PROVIDER：{name}")
