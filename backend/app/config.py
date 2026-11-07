
"""集中式設定：外部服務、限制與密鑰皆由環境變數讀取。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """小照系統設定。"""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: str = "dev"
    tz_name: str = "Asia/Taipei"
    database_url: str = Field(...)
    test_database_url: str = ""
    data_dir: Path = Path("F:/appdata/ltc_care/data")

    secret_key: str = Field(default="", min_length=0)
    data_encryption_key: str = ""
    public_base_url: str = "http://127.0.0.1:8140"
    internal_health_token: str = ""

    line_mode: str = "mock"
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_login_channel_id: str = ""
    liff_id: str = ""

    # Google Gemma 4 文字生成
    llm_provider: str = "ollama"
    llm_model: str = "gemma4:e4b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    llm_timeout_sec: float = 60.0

    # Google EmbeddingGemma 2
    embedding_provider: str = "ollama"
    embedding_model: str = "embeddinggemma-2:270m"
    embedding_dim: int = 768
    embedding_timeout_sec: float = Field(default=120.0, gt=0)
    embedding_batch_size: int = Field(default=8, ge=1, le=32)

    # 語音辨識與合成
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
    wake_words: str = (
        "小照你好,小照您好,小照妳好,"
        "小昭你好,小昭您好,"
        "小趙你好,小趙您好,"
        "小照,小昭,小趙"
    )

    question_max_sec: int = 60
    conversation_max_sec: int = 600
    max_upload_mb: int = 30
    audio_ttl_min: int = 30
    draft_ttl_hours: int = 24
    tts_ttl_hours: int = 24
    session_ttl_hours: int = 12

    log_level: str = "INFO"
    ffmpeg_dir: str = ""

    @field_validator("llm_model")
    @classmethod
    def _only_gemma_llm(cls, value: str) -> str:
        if value != "gemma4:e4b":
            raise ValueError(
                "AgeTech 參賽版只允許 LLM_MODEL=gemma4:e4b"
            )
        return value

    @field_validator("embedding_model")
    @classmethod
    def _only_gemma_embedding(cls, value: str) -> str:
        if value != "embeddinggemma-2:270m":
            raise ValueError(
                "AgeTech 參賽版只允許 "
                "EMBEDDING_MODEL=embeddinggemma-2:270m"
            )
        return value

    @field_validator("embedding_dim")
    @classmethod
    def _check_embedding_dim(cls, value: int) -> int:
        if value != 768:
            raise ValueError(
                "Embedding 維度必須為 768；"
                "請同步執行資料庫 Migration"
            )
        return value

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
        return self.app_env == "production"

    @property
    def dev_features_enabled(self) -> bool:
        return (
            not self.is_production
            and self.line_mode == "mock"
        )

    @property
    def api_docs_enabled(self) -> bool:
        """正式環境關閉公開 API 文件（/api/docs、/api/redoc、/api/openapi.json）；開發/測試環境維持開放。"""
        return not self.is_production

    def provider_modes(self) -> dict[str, str]:
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
    settings = Settings()

    if settings.is_production:
        missing = [
            name
            for name in (
                "secret_key",
                "data_encryption_key",
                "line_channel_secret",
            )
            if not getattr(settings, name)
        ]

        if missing:
            raise RuntimeError(
                "正式環境缺少必要設定："
                + ", ".join(missing)
            )

    return settings
