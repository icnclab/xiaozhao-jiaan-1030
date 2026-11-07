"""健康檢查資料蒐集：單一來源，給公開精簡端點與授權完整端點共用。

公開端點只能回傳 collect_health() 結果裡不含內部設定的那個子集（見
app.main.healthz）；資料庫名稱、provider 模式等內部設定只能透過授權端點
（app.api.admin_routes.healthz_detail）或本機直接呼叫 collect_health()
取得，不得經由未授權的 HTTP 回應外流。
"""

from __future__ import annotations

import hmac
import secrets

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import REPO_ROOT, get_settings

# 本機既有的啟動／重啟健康檢查腳本（deploy/fieldtest/*.ps1）在 Funnel 公開之前，
# 一直是直接呼叫未授權的 /api/healthz 取得 database_name、provider 模式等欄位。
# 現在公開端點改成精簡版，這些腳本改用同一個端點＋這個本機專用 Token（放在既有、
# 已被 .gitignore 排除的 deploy/fieldtest/run/ 目錄，不進版控，也不是帳號密碼）
# 才能拿到完整內容，等同於原地加一道「只有本機才知道」的授權，不需要改腳本呼叫的
# 網址或新增登入流程。
_TOKEN_FILE = REPO_ROOT / "deploy" / "fieldtest" / "run" / "internal_health_token.txt"


def _local_internal_health_token() -> str:
    """回傳本機用的 internal health token：環境變數優先，否則用／建立本機檔案。"""
    configured = get_settings().internal_health_token
    if configured:
        return configured
    try:
        if _TOKEN_FILE.is_file():
            existing = _TOKEN_FILE.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(32)
        _TOKEN_FILE.write_text(token, encoding="utf-8")
        return token
    except OSError:
        # 本機檔案系統異常時寧可停用這個授權捷徑（一律回精簡版），不要整台 API 掉線。
        return ""


def internal_health_token_matches(provided: str | None) -> bool:
    """比對呼叫端帶來的 Token 是否等於本機 Token；常數時間比較，避免時間側漏。"""
    if not provided:
        return False
    expected = _local_internal_health_token()
    return bool(expected) and hmac.compare_digest(provided, expected)


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
