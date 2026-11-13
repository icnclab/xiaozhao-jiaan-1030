"""健康檢查資料蒐集：單一來源，給公開精簡端點與授權完整端點共用。

公開端點只能回傳 collect_health() 結果裡不含內部設定的那個子集（見
app.main.healthz）；資料庫名稱、provider 模式等內部設定只能透過授權端點
（app.api.admin_routes.healthz_detail）或本機直接呼叫 collect_health()
取得，不得經由未授權的 HTTP 回應外流。

本機健康檢查 Token（給 deploy/fieldtest/*.ps1 等既有腳本用）在應用程式啟動時
由 ensure_internal_health_token()（app.main 的 lifespan 呼叫）主動初始化一次，
跟任何一次 HTTP 請求無關：
- 不會因為有人（包含未授權的公開 Funnel 請求）打 /api/healthz 而產生或改變。
- internal_health_token_matches() 只做比對，初始化沒完成前一律回 False
  （退回精簡版），绝不會在請求路徑裡觸發產生 Token 這個副作用。
這樣設計是為了避免「要先有人帶對 Token 來才生得出 Token」的先有雞先有蛋問題，
同時確保 Token 的產生時機跟「誰打了 API」完全脫鉤。
"""

from __future__ import annotations

import hmac
import logging
import os
import platform
import subprocess
import threading

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import REPO_ROOT, get_settings

logger = logging.getLogger(__name__)

_TOKEN_FILE = REPO_ROOT / "deploy" / "fieldtest" / "run" / "internal_health_token.txt"
_token_lock = threading.Lock()
_cached_token: str | None = None


def _restrict_token_file_permissions() -> None:
    """盡量把 Token 檔案鎖到只有目前帳號可讀；失敗只記警告，不擋啟動。"""
    try:
        if platform.system() == "Windows":
            username = os.environ.get("USERNAME", "")
            if username:
                # 拿掉繼承、只留目前帳號一條授權：其他帳號完全沒有存取權。給 M（修改）
                # 不是只給 R，是因為執行這支程式的同一個帳號之後可能還要重新整理/輪替
                # 這個檔案；只給唯讀會連自己都鎖死，之後想换 Token 還要額外處理權限。
                subprocess.run(
                    ["icacls", str(_TOKEN_FILE), "/inheritance:r", "/grant:r", f"{username}:M"],
                    capture_output=True, timeout=5, check=False,
                )
        else:
            os.chmod(_TOKEN_FILE, 0o600)
    except OSError:
        logger.warning("could not restrict internal health token file permissions")


def ensure_internal_health_token() -> str:
    """應用程式啟動時呼叫一次：準備好本機健康檢查 Token。

    環境變數 INTERNAL_HEALTH_TOKEN 優先；否則讀取既有本機檔案，檔案不存在才
    產生一個新的高強度隨機值（secrets.token_hex(32)，256 bit）並寫入——這個
    寫入動作只會在「應用程式啟動」這個受控時機發生一次，不受任何 HTTP 請求觸發
    或影響。Token 本身只寫入本機檔案，不記錄進任何 log、不回應在任何 API 內容裡。
    """
    global _cached_token
    with _token_lock:
        if _cached_token is not None:
            return _cached_token
        configured = get_settings().internal_health_token
        if configured:
            _cached_token = configured
            return _cached_token
        try:
            _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            if _TOKEN_FILE.is_file():
                existing = _TOKEN_FILE.read_text(encoding="utf-8").strip()
                if existing:
                    _cached_token = existing
                    _restrict_token_file_permissions()
                    return _cached_token
            import secrets as _secrets
            token = _secrets.token_hex(32)
            _TOKEN_FILE.write_text(token, encoding="utf-8")
            _restrict_token_file_permissions()
            _cached_token = token
            logger.info("internal health token initialized at startup (value not logged)")
            return _cached_token
        except OSError:
            logger.warning("internal health token file unavailable; healthz stays minimal for every caller")
            _cached_token = ""
            return _cached_token


def internal_health_token_matches(provided: str | None) -> bool:
    """比對呼叫端帶來的 Token 是否等於本機 Token；常數時間比較，避免時間側漏。

    初始化完成前（_cached_token 還是 None）一律回 False，不會在這裡補做初始化——
    初始化只能由 ensure_internal_health_token() 在啟動時觸發，不受任何請求影響，
    包含帶著亂猜 Token 來試的未授權公開請求。
    """
    if not provided or _cached_token is None:
        return False
    return hmac.compare_digest(provided, _cached_token)


def collect_health(db: Session) -> dict:
    """回傳完整健康資訊（含資料庫名稱、provider 模式）。內部使用，不得直接公開。"""
    database_name = db.execute(text("SELECT current_database()")).scalar_one()
    age = db.execute(text("SELECT EXTRACT(EPOCH FROM now() - max(seen_at)) FROM worker_heartbeats")).scalar()
    worker_heartbeat_age_sec = round(float(age), 1) if age is not None else None
    return {
        "db": "ok",
        "database_name": database_name,
        "modes": get_settings().provider_modes(),
        "worker_heartbeat_age_sec": worker_heartbeat_age_sec,
    }


def collect_health_public(db: Session) -> dict:
    """公開端點用的精簡子集：保留既有腳本依賴的 db 狀態與 worker 心跳秒數欄位名稱，
    只拿掉 database_name 與 modes（provider 名稱）這兩個真正算內部設定的欄位。"""
    full = collect_health(db)
    return {"db": full["db"], "worker_heartbeat_age_sec": full["worker_heartbeat_age_sec"]}


def collect_health_for_request(db: Session, internal_health_token: str | None) -> dict:
    """依是否帶正確的本機 Token，回傳完整或精簡版本；提供未授權呼叫端一律精簡。"""
    if internal_health_token_matches(internal_health_token):
        return collect_health(db)
    return collect_health_public(db)
