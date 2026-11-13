"""Tailscale Funnel 公開端點收斂：/api/docs、/api/redoc、/api/openapi.json、/api/healthz。

驗證：
- 正式環境（APP_ENV=production）關閉 API 文件三個入口；非正式環境維持開放。
- 公開 /api/healthz 不洩漏 database_name、provider 模式；帶對的本機 Token 才拿得到。
- /api/admin/healthz 需要管理員登入，一般角色與未登入都拒絕。
"""

from __future__ import annotations

from app.config import Settings
from tests.conftest import login_web


def test_api_docs_enabled_follows_production_flag():
    """正式環境關閉文件；非正式環境（dev/test）保留，給開發與測試使用。"""
    base = {"database_url": "postgresql://x/y"}
    assert Settings(app_env="production", **base).api_docs_enabled is False
    assert Settings(app_env="dev", **base).api_docs_enabled is True
    assert Settings(app_env="test", **base).api_docs_enabled is True


def test_docs_endpoints_available_in_non_production_test_env(client):
    """目前測試環境 APP_ENV=test（非正式環境），文件三個入口都應該還在。"""
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/redoc").status_code == 200
    assert client.get("/api/openapi.json").status_code == 200


def test_public_healthz_hides_internal_settings(client):
    """未帶任何授權資訊的呼叫（等同經 Tailscale Funnel 進來的公開請求）：
    只能看到 db 狀態與 worker 心跳秒數，看不到 database_name 或 provider 模式。"""
    body = client.get("/api/healthz").json()
    assert set(body.keys()) == {"db", "worker_heartbeat_age_sec"}
    assert body["db"] == "ok"
    assert "database_name" not in body
    assert "modes" not in body


def test_public_healthz_wrong_token_still_minimal(client):
    """帶錯的 Token 跟完全不帶 Token 一樣，拿到精簡版，不會洩漏內部設定。"""
    body = client.get("/api/healthz", headers={"X-Internal-Health-Token": "not-the-real-token"}).json()
    assert set(body.keys()) == {"db", "worker_heartbeat_age_sec"}


def test_healthz_with_internal_token_returns_full_detail(client):
    """本機啟動／重啟腳本帶對的 Token（conftest 設定的 test-internal-health-token），
    拿回原本的完整欄位，確保既有腳本相容。"""
    body = client.get("/api/healthz", headers={"X-Internal-Health-Token": "test-internal-health-token"}).json()
    assert body["db"] == "ok"
    assert "database_name" in body
    assert "modes" in body
    assert set(body["modes"].keys()) == {"llm", "embedding", "stt", "tts", "diarization", "line"}
    assert body["worker_heartbeat_age_sec"] == body["worker_heartbeat_age_sec"]  # 與公開版同一欄位


def test_admin_healthz_requires_login(client):
    """未登入打管理員專用的完整健康檢查端點：401。"""
    assert client.get("/api/admin/healthz").status_code == 401


def test_admin_healthz_denies_non_admin_role(client, world):
    """督導不是 admin 角色，不能看完整健康檢查內容。"""
    headers = login_web(client, "sup_a")
    assert client.get("/api/admin/healthz", headers=headers).status_code == 403


def test_admin_healthz_allows_admin(client, world):
    """admin 角色登入後，/api/admin/healthz 回完整內容，跟帶正確本機 Token 拿到的一樣。"""
    headers = login_web(client, "admin_happy")
    response = client.get("/api/admin/healthz", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "database_name" in body
    assert "modes" in body
