"""喚醒詞：剝除稱呼、同音容錯、純打招呼判定；三個入口行為一致。"""

from __future__ import annotations

import pytest

from app.services.wake import strip_wake_word
from tests.conftest import login_liff, new_id


@pytest.mark.parametrize(
    ("raw", "expected", "matched"),
    [
        ("小照你好，家屬要我代購成藥可以嗎？", "家屬要我代購成藥可以嗎？", True),
        ("小照您好 照護紀錄要保存多久", "照護紀錄要保存多久", True),
        ("嘿，小照你好：夜間人力比例？", "夜間人力比例？", True),
        ("小昭你好家屬要求多餵一餐怎麼辦", "家屬要求多餵一餐怎麼辦", True),  # ASR 同音
        ("小趙你好,照護記錄要儲存多久?", "照護記錄要儲存多久?", True),  # faster-whisper 實際輸出
        ("小照 交班要交接什麼", "交班要交接什麼", True),
        ("家屬要我代購成藥可以嗎？", "家屬要我代購成藥可以嗎？", False),
        ("你好小照", "你好小照", False),  # 只認句首
    ],
)
def test_strip_wake_word(raw: str, expected: str, matched: bool) -> None:
    result = strip_wake_word(raw)
    assert result.text == expected
    assert result.matched is matched
    assert result.greeting_only is False


@pytest.mark.parametrize("raw", ["小照你好", "小照你好！", "嘿 小照", "小昭您好～"])
def test_greeting_only(raw: str) -> None:
    result = strip_wake_word(raw)
    assert result.matched and result.greeting_only and result.text == ""


def test_liff_question_with_wake_word(client, world):
    headers = login_liff(client, "cg1")
    data = client.post("/api/qa/ask", headers=headers, json={
        "question": "小照你好，照護紀錄要保存多久？", "client_request_id": new_id()}).json()
    assert data["outcome"] == "answered"
    assert data["question_masked"] == "照護紀錄要保存多久？"
    assert data["wake_word"] is True


def test_liff_greeting_only_rejected_with_hint(client, world):
    headers = login_liff(client, "cg1")
    response = client.post("/api/qa/ask", headers=headers, json={"question": "小照你好", "client_request_id": new_id()})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "greeting_only"


def test_public_config_exposes_wake_words(client, world):
    config = client.get("/api/config/public").json()
    assert config["bot_name"] == "小照"
    assert "小照你好" in config["wake_words"]
