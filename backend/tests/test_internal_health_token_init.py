"""本機健康檢查 Token 初始化：修正「要先有人帶對 Token 來才生得出 Token」的先有雞先有蛋問題。

涵蓋：首次啟動產生、Token 不存在時的比對行為、既有檔案沿用、正確/錯誤 Token 比對、
並行初始化一致性。全部直接測 app.services.health 模組本身，不經過真正的 HTTP 請求，
確保「初始化」跟「請求處理」完全是兩件事。
"""

from __future__ import annotations

import threading

import pytest

from app.services import health as health_module


@pytest.fixture(autouse=True)
def _reset_token_cache():
    """每個測試前清掉模組快取、測試後還原成原本的值（conftest.py 在啟動時已經初始化
    過一次），不讓這個檔案的測試把快取清空後遺留給同一個 pytest session 裡其他測試
    檔案，造成它們以為 Token 還沒初始化。"""
    original = health_module._cached_token
    health_module._cached_token = None
    yield
    health_module._cached_token = original


@pytest.fixture
def isolated_token_file(tmp_path, monkeypatch):
    """把 Token 檔案位置換到 tmp_path，且把設定值強制清空，模擬「尚未設定環境變數、
    尚未有本機檔案」的首次啟動情境，不會動到真正的 deploy/fieldtest/run/ 目錄。"""
    token_file = tmp_path / "internal_health_token.txt"
    monkeypatch.setattr(health_module, "_TOKEN_FILE", token_file)
    monkeypatch.setattr(health_module, "_restrict_token_file_permissions", lambda: None)

    class _FakeSettings:
        internal_health_token = ""

    monkeypatch.setattr(health_module, "get_settings", lambda: _FakeSettings())
    return token_file


def test_first_boot_creates_token_file_with_strong_random_value(isolated_token_file):
    """首次啟動：檔案不存在，ensure_internal_health_token() 自己產生，不依賴任何請求先帶 Token 來。"""
    assert not isolated_token_file.is_file()
    token = health_module.ensure_internal_health_token()
    assert isolated_token_file.is_file()
    assert len(token) == 64  # secrets.token_hex(32) -> 64 個十六進位字元 = 256 bit
    assert isolated_token_file.read_text(encoding="utf-8").strip() == token


def test_token_not_exist_before_init_matches_nothing_and_has_no_side_effect():
    """初始化前（_cached_token 仍是 None）：帶任何 Token 一律比對不過，且比對本身不會觸發產生。"""
    assert health_module._cached_token is None
    assert health_module.internal_health_token_matches("anything-including-a-guess") is False
    assert health_module._cached_token is None


def test_existing_token_file_is_reused_not_regenerated(isolated_token_file):
    """Token 檔案已存在：直接沿用既有值，不會被覆寫成新的隨機值。"""
    isolated_token_file.parent.mkdir(parents=True, exist_ok=True)
    isolated_token_file.write_text("existing-token-value", encoding="utf-8")
    token = health_module.ensure_internal_health_token()
    assert token == "existing-token-value"


def test_correct_token_matches_after_init(isolated_token_file):
    token = health_module.ensure_internal_health_token()
    assert health_module.internal_health_token_matches(token) is True


def test_wrong_token_does_not_match_after_init(isolated_token_file):
    health_module.ensure_internal_health_token()
    assert health_module.internal_health_token_matches("not-the-real-token") is False
    assert health_module.internal_health_token_matches("") is False
    assert health_module.internal_health_token_matches(None) is False


def test_concurrent_initialization_yields_single_consistent_token(isolated_token_file):
    """並行初始化：多個執行緒同時搶著呼叫，最後只會有一個值，不會互相覆寫出不一致的結果。"""
    results: list[str] = []

    def worker() -> None:
        results.append(health_module.ensure_internal_health_token())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(results)) == 1
    assert len(results[0]) == 64
    assert isolated_token_file.read_text(encoding="utf-8").strip() == results[0]


def test_configured_env_token_takes_priority_over_file(tmp_path, monkeypatch):
    """INTERNAL_HEALTH_TOKEN 環境變數有值時，優先使用它，不去讀寫本機檔案。"""
    token_file = tmp_path / "internal_health_token.txt"
    monkeypatch.setattr(health_module, "_TOKEN_FILE", token_file)

    class _FakeSettings:
        internal_health_token = "configured-from-env"

    monkeypatch.setattr(health_module, "get_settings", lambda: _FakeSettings())
    token = health_module.ensure_internal_health_token()
    assert token == "configured-from-env"
    assert not token_file.is_file()
