"""集中式設定：所有外部服務、限制與密鑰都從環境變數（.env）讀取。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """應用程式設定。

    Attributes:
        app_env: dev、test 或 production；production 會關閉 dev-login 與模擬端點。
        database_url: SQLAlchemy 連線字串（psycopg3）。
        data_dir: 音訊暫存、TTS 快取、上傳原檔的根目錄。
        line_mode: mock 或 real。mock 模式仍會真實驗證 webhook 簽章。
    """

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    app_env: str = "dev"
    tz_name: str = "Asia/Taipei"
    database_url: str = Field(...)
    test_database_url: str = ""
    data_dir: Path = Path("F:/appdata/ltc_care/data")

    secret_key: str = Field(default="", min_length=0)
    data_encryption_key: str = ""
    public_base_url: str = "http://127.0.0.1:8140"

    line_mode: str = "mock"
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_login_channel_id: str = ""
    liff_id: str = ""

    llm_provider: str = "extractive"
    llm_model: str = "gemma4:e4b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    llm_timeout_sec: float = 60.0

    embedding_provider: str = "hash"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    stt_provider: str = "mock"
    stt_base_url: str = "http://127.0.0.1:8147"
    stt_model: str = "large-v3"
    stt_timeout_sec: float = 600.0

    tts_provider: str = "mock"
    tts_voice: str = "Microsoft Hanhan Desktop"
    diarization_provider: str = "none"

    cht_stt_endpoint: str = ""
    cht_tts_endpoint: str = ""
    cht_api_key: str = ""

    bot_name: str = "小照"
    # 含 STT 常見同音誤辨（小昭、小趙；實測 faster-whisper medium 會把「小照」聽成「小趙」）
    wake_words: str = "小照你好,小照您好,小照妳好,小昭你好,小昭您好,小趙你好,小趙您好,小照,小昭,小趙"

    question_max_sec: int = 60
    conversation_max_sec: int = 600
    max_upload_mb: int = 30
    audio_ttl_min: int = 30
    draft_ttl_hours: int = 24
    tts_ttl_hours: int = 24
    session_ttl_hours: int = 12

    log_level: str = "INFO"
    ffmpeg_dir: str = ""  # 內建 ffmpeg/ffprobe 所在目錄（安裝包 bin\）；空則用 PATH

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("DATABASE_URL must not be blank")
        return value

    @field_validator("line_mode")
    @classmethod
    def _check_line_mode(cls, value: str) -> str:
        if value not in {"mock", "real"}:
            raise ValueError("LINE_MODE 只能是 mock 或 real")
        return value

    @property
    def is_production(self) -> bool:
        """是否為正式環境。"""
        return self.app_env == "production"

    @property
    def dev_features_enabled(self) -> bool:
        """dev-login 與 LINE 模擬端點只在非正式環境＋mock 模式開放。"""
        return (not self.is_production) and self.line_mode == "mock"

    def provider_modes(self) -> dict[str, str]:
        """回報各 provider 的實際模式，供 API 回應與畫面標示。"""
        return {
            "llm": self.llm_provider,
            "embedding": self.embedding_provider,
            "stt": self.stt_provider,
            "tts": self.tts_provider,
            "diarization": self.diarization_provider,
            "line": self.line_mode,
        }


@lru_cache
def get_settings() -> Settings:
    """取得（快取的）設定物件。"""
    settings = Settings()
    if settings.is_production:
        missing = [
            name
            for name in ("secret_key", "data_encryption_key", "line_channel_secret")
            if not getattr(settings, name)
        ]
        if missing:
            raise RuntimeError(f"正式環境缺少必要設定：{', '.join(missing)}")
    return settings
