"""喚醒詞（稱呼層）：機器人叫「小照」，「小照你好，…」視為對小照提問。

三個入口共用同一套規則：LINE 聊天文字、LINE 語音轉錄、LIFF 語音／文字提問。
喚醒詞清單走設定（`WAKE_WORDS`，逗號分隔），含 ASR 常見同音（小昭）；不寫死於介面。

只做「剝除稱呼」，不做任何語意判斷：剝完是空字串代表純打招呼，由呼叫端決定回什麼。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.config import get_settings

# 喚醒詞前後允許的贅字與標點：「嘿，小照你好：請問…」→ 問題本體
_LEADING_JUNK = re.compile(r"^[\s,，、。:：!！?？~～]+")
_LEADING_HEY = re.compile(r"^(?:嘿|欸|喂|哈囉|哈羅|hey|hi|hello)\s*[,，、]?\s*", re.IGNORECASE)


@dataclass(frozen=True)
class WakeResult:
    """喚醒詞剝除結果。

    Attributes:
        text: 剝除喚醒詞後的問題本體（可能為空字串）。
        matched: 是否偵測到喚醒詞。
        greeting_only: 偵測到喚醒詞但沒有問題本體（純打招呼）。
    """

    text: str
    matched: bool

    @property
    def greeting_only(self) -> bool:
        """是否只有打招呼、沒有問題。"""
        return self.matched and not self.text


def wake_words() -> list[str]:
    """設定中的喚醒詞，長的在前（避免「小照」先吃掉「小照你好」的前半）。"""
    raw = get_settings().wake_words
    words = [unicodedata.normalize("NFKC", w).strip() for w in raw.split(",")]
    unique = list(dict.fromkeys(w for w in words if w))  # 去重但保留設定順序（第一個是畫面上的示範用語）
    return sorted(unique, key=len, reverse=True)  # 穩定排序：同長度維持設定順序


def strip_wake_word(text: str) -> WakeResult:
    """剝除句首喚醒詞。

    Args:
        text: 使用者原文（文字或轉錄）。

    Returns:
        剝除結果；沒有喚醒詞時 `text` 原樣回傳（只去頭尾空白）。
    """
    original = (text or "").strip()
    # 只在「比對」時做 NFKC（全形→半形），回傳的問題本體保留原文字元（例如全形問號）
    candidate = _LEADING_HEY.sub("", _LEADING_JUNK.sub("", original))
    for word in wake_words():
        prefix = candidate[: len(word)]
        if unicodedata.normalize("NFKC", prefix).lower() == word.lower():
            rest = _LEADING_JUNK.sub("", candidate[len(word):])
            return WakeResult(text=rest.strip(), matched=True)
    return WakeResult(text=original, matched=False)


def greeting_reply() -> str:
    """純打招呼時的回覆文字。"""
    name = get_settings().bot_name
    return (f"我是{name}，請直接說出或輸入您的問題，例如「{name}你好，家屬要我代購成藥可以嗎？」。\n"
            "我只回答規範查詢並附出處；醫療、用藥與補助金額問題會轉督導。")
