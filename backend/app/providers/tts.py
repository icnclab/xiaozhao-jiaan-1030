"""TTS provider adapters。輸出一律是 wav，後續由 audio.to_m4a 轉檔。

- `sapi`：Windows 內建語音（預設 Microsoft Hanhan Desktop，zh-TW），本機、零網路。只在 Windows 主機可用。
- `mock`：產生一段短音調，測試播放與流程用。
- `cht`：中華電信 TTS 保留 adapter（**未串接**）。
"""

from __future__ import annotations

import math
import os
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Protocol

from app.config import get_settings


class TtsNotAvailable(RuntimeError):
    """TTS provider 不可用。"""


class TtsProvider(Protocol):
    """TTS adapter 介面。"""

    name: str

    def synthesize(self, text: str, wav_out: Path) -> Path:
        """把文字合成 wav。"""
        ...


_SAPI_SCRIPT = r"""
param([string]$TextFile, [string]$OutFile, [string]$Voice)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $s.SelectVoice($Voice) } catch { throw "voice-not-found" }
$s.Rate = 0
$s.SetOutputToWaveFile($OutFile)
$s.Speak([System.IO.File]::ReadAllText($TextFile, [System.Text.Encoding]::UTF8))
$s.Dispose()
"""


class SapiTts:
    """Windows SAPI（System.Speech）本機語音合成。"""

    name = "sapi"

    def __init__(self, voice: str) -> None:
        self.voice = voice

    def synthesize(self, text: str, wav_out: Path) -> Path:
        """見 `TtsProvider.synthesize`。

        Raises:
            TtsNotAvailable: 非 Windows 或語音不存在。
        """
        if os.name != "nt":
            raise TtsNotAvailable("SAPI 只能在 Windows 主機使用")
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "tts.ps1"
            text_file = Path(tmp) / "text.txt"
            # 文字經檔案以 UTF-8 傳遞，避免命令列編碼（cp950）問題；BOM 讓 PS 5.1 正確讀腳本
            script.write_text(_SAPI_SCRIPT, encoding="utf-8-sig")
            text_file.write_text(text, encoding="utf-8")
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(script), str(text_file), str(wav_out), self.voice],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
            )
        if result.returncode != 0 or not wav_out.exists():
            raise TtsNotAvailable("SAPI 合成失敗" + (": voice-not-found" if "voice-not-found" in result.stderr else ""))
        return wav_out


class MockTts:
    """測試用 TTS：依字數產生 440 Hz 短音。`fail` 設為 True 可模擬失敗。"""

    name = "mock"
    fail: bool = False

    def synthesize(self, text: str, wav_out: Path) -> Path:
        """見 `TtsProvider.synthesize`。"""
        if MockTts.fail:
            raise TtsNotAvailable("模擬 TTS 失敗")
        rate, seconds = 16000, min(1.0 + len(text) * 0.05, 5.0)
        with wave.open(str(wav_out), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            frames = b"".join(
                struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / rate)))
                for i in range(int(rate * seconds))
            )
            handle.writeframes(frames)
        return wav_out


class ChtTts:
    """中華電信 TTS 保留 adapter（未串接）。"""

    name = "cht"

    def synthesize(self, text: str, wav_out: Path) -> Path:
        """見 `TtsProvider.synthesize`。

        Raises:
            TtsNotAvailable: 永遠拋出，直到依官方文件完成串接。
        """
        raise TtsNotAvailable("中華電信 TTS adapter 尚未依官方文件實作，未串接")


def get_tts_provider() -> TtsProvider:
    """依設定建立 TTS provider。"""
    settings = get_settings()
    if settings.tts_provider == "sapi":
        return SapiTts(settings.tts_voice)
    if settings.tts_provider == "mock":
        return MockTts()
    if settings.tts_provider == "cht":
        return ChtTts()
    raise RuntimeError(f"未知的 TTS_PROVIDER：{settings.tts_provider}")
