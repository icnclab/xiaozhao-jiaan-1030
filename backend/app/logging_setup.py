"""日誌設定：一般日誌只記事件摘要，並以過濾器遮蔽疑似 token 與長字串。

原則（見 docs/data-flow.md）：不記金鑰、完整 webhook、未遮罩談話、token。
程式碼端的紀律是「不把內容傳給 logger」；本過濾器是第二道防線。
"""

from __future__ import annotations

import logging
import re

from app.config import get_settings

_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}")
_MEDIA_PATH = re.compile(r"(/api/media/tts/)[^\s\"'?]+")
_LONG_TOKEN = re.compile(r"[A-Za-z0-9_\-]{40,}")
_KV_SECRET = re.compile(r"(?i)((?:token|secret|password|key|signature)[\"'=:\s]+)[^\s,\"'}]{6,}")


class RedactingFilter(logging.Filter):
    """把 log 訊息中的 token、密鑰樣式字串替換成 [REDACTED]。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """改寫訊息後放行。

        Args:
            record: 日誌紀錄。

        Returns:
            永遠 True（只改寫不丟棄）。
        """
        message = record.getMessage()
        message = _BEARER.sub(r"\1[REDACTED]", message)
        message = _MEDIA_PATH.sub(r"\1[REDACTED]", message)
        message = _KV_SECRET.sub(r"\1[REDACTED]", message)
        message = _LONG_TOKEN.sub("[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def setup_logging() -> None:
    """設定根 logger（冪等）。"""
    root = logging.getLogger()
    if getattr(root, "_ltc_configured", False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    root.handlers = [handler]
    root.setLevel(get_settings().log_level)
    # uvicorn access log 會印出完整 URL（含媒體簽章 token），交給同一個過濾器
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False
    root._ltc_configured = True  # type: ignore[attr-defined]
