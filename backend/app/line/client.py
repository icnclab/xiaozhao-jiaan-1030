"""LINE Messaging API client（real／mock）。

- 只連官方固定網域：`api.line.me`（reply、push、quota）與 `api-data.line.me`（使用者上傳內容）。
  不接受任何外部 URL 參數，webhook 中 `contentProvider.type = external` 的連結不下載（防 SSRF）。
- push 帶 `X-Line-Retry-Key`；409 代表同一請求已被受理，視為成功。
- 200 只代表 LINE 平臺受理，**不代表送達**（官方文件：已封鎖者也會回 200）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LineMockOutbox

API_BASE = "https://api.line.me"
DATA_API_BASE = "https://api-data.line.me"
MAX_CONTENT_BYTES = 30 * 1024 * 1024
_MESSAGE_ID_RE = re.compile(r"^[0-9]{1,32}$")


@dataclass(frozen=True)
class SendResult:
    """reply／push 結果。

    Attributes:
        accepted: LINE 平臺是否受理（不代表送達）。
        status_code: HTTP 狀態碼（mock 為 200）。
        error_code: 失敗時的代碼（rate_limited、bad_request、auth、network…）。
        retryable: 失敗是否值得重試。
    """

    accepted: bool
    status_code: int
    error_code: str | None = None
    retryable: bool = False


class ContentUnavailable(Exception):
    """內容無法取得（過期、被收回或非 LINE 託管）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class LineClient(Protocol):
    """LINE client 介面。"""

    mode: str

    def reply(self, reply_token: str, messages: list[dict[str, Any]]) -> SendResult:
        """回覆訊息。"""
        ...

    def push(self, to: str, messages: list[dict[str, Any]], retry_key: str) -> SendResult:
        """推播訊息。"""
        ...

    def get_content(self, message_id: str) -> bytes:
        """取得使用者上傳的內容。"""
        ...


def _classify(status: int) -> SendResult:
    if status == 200 or status == 409:
        return SendResult(accepted=True, status_code=status)
    if status == 429:
        return SendResult(False, status, "rate_limited_or_quota", retryable=True)
    if status in (401, 403):
        return SendResult(False, status, "auth", retryable=False)
    if status == 400:
        return SendResult(False, status, "bad_request", retryable=False)
    if status >= 500:
        return SendResult(False, status, "server_error", retryable=True)
    return SendResult(False, status, f"http_{status}", retryable=False)


class RealLineClient:
    """呼叫真實 LINE API。"""

    mode = "real"

    def __init__(self, access_token: str) -> None:
        if not access_token:
            raise RuntimeError("LINE_MODE=real 但未設定 LINE_CHANNEL_ACCESS_TOKEN")
        self._headers = {"Authorization": f"Bearer {access_token}"}

    def reply(self, reply_token: str, messages: list[dict[str, Any]]) -> SendResult:
        """見 `LineClient.reply`。"""
        if get_settings().is_uat:
            return SendResult(False, 403, "uat_reply_disabled", False)
        try:
            response = httpx.post(f"{API_BASE}/v2/bot/message/reply", headers=self._headers,
                                  json={"replyToken": reply_token, "messages": messages}, timeout=10)
        except httpx.HTTPError:
            return SendResult(False, 0, "network", retryable=False)  # reply token 單次有效，不重試
        return _classify(response.status_code)

    def push(self, to: str, messages: list[dict[str, Any]], retry_key: str) -> SendResult:
        """見 `LineClient.push`。"""
        from app.uat import push_allowed, messages_allowed
        if not push_allowed(get_settings(), to) or not messages_allowed(get_settings(), messages):
            return SendResult(False, 403, "uat_push_blocked", False)
        headers = dict(self._headers, **{"X-Line-Retry-Key": retry_key})
        try:
            response = httpx.post(f"{API_BASE}/v2/bot/message/push", headers=headers,
                                  json={"to": to, "messages": messages}, timeout=10)
        except httpx.HTTPError:
            return SendResult(False, 0, "network", retryable=True)
        return _classify(response.status_code)

    def get_content(self, message_id: str) -> bytes:
        """見 `LineClient.get_content`。只打官方內容端點，限制大小。"""
        if get_settings().is_uat:
            raise ContentUnavailable("uat_line_download_disabled", "Use LIFF upload in UAT")
        if not _MESSAGE_ID_RE.match(message_id):
            raise ContentUnavailable("invalid_id", "訊息 ID 格式不正確")
        with httpx.stream("GET", f"{DATA_API_BASE}/v2/bot/message/{message_id}/content",
                          headers=self._headers, timeout=30) as response:
            if response.status_code in (404, 410):
                raise ContentUnavailable("gone", "LINE 上的語音已不存在或已過期")
            response.raise_for_status()
            chunks, total = [], 0
            for piece in response.iter_bytes():
                total += len(piece)
                if total > MAX_CONTENT_BYTES:
                    raise ContentUnavailable("too_large", "語音檔過大")
                chunks.append(piece)
        return b"".join(chunks)


class MockLineClient:
    """模擬模式：reply／push 寫入 line_mock_outbox，內容從本機模擬內容區讀取。"""

    mode = "mock"
    # 測試用：強制 push 回傳指定狀態碼
    force_push_status: int | None = None

    def __init__(self, session: Session) -> None:
        self.session = session

    def reply(self, reply_token: str, messages: list[dict[str, Any]]) -> SendResult:
        """見 `LineClient.reply`。"""
        self.session.add(LineMockOutbox(kind="reply", to=f"replyToken:{reply_token[:8]}…", messages=messages))
        self.session.flush()
        return SendResult(True, 200)

    def push(self, to: str, messages: list[dict[str, Any]], retry_key: str) -> SendResult:
        """見 `LineClient.push`。"""
        if MockLineClient.force_push_status is not None:
            return _classify(MockLineClient.force_push_status)
        self.session.add(LineMockOutbox(kind="push", to=to, messages=messages, retry_key=retry_key))
        self.session.flush()
        return SendResult(True, 200)

    def get_content(self, message_id: str) -> bytes:
        """見 `LineClient.get_content`。"""
        if not _MESSAGE_ID_RE.match(message_id):
            raise ContentUnavailable("invalid_id", "訊息 ID 格式不正確")
        path = mock_content_path(message_id)
        if not path.exists():
            raise ContentUnavailable("gone", "（模擬）語音內容不存在或已清除")
        return path.read_bytes()


def mock_content_path(message_id: str) -> Path:
    """模擬模式下使用者語音內容的存放路徑。"""
    folder = get_settings().data_dir / "mock_line_content"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{message_id}.bin"


def get_line_client(session: Session) -> LineClient:
    """依 LINE_MODE 建立 client。"""
    settings = get_settings()
    if settings.line_mode == "real":
        return RealLineClient(settings.line_channel_access_token)
    return MockLineClient(session)
