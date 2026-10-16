"""中文文字工具：正規化、字元雙連詞（bigram）、支持度計算。

為什麼用雙連詞：PostgreSQL 內建全文檢索不會斷中文詞；把「移位協助」拆成
「移位 位協 協助」三個 token 後，用 `simple` 設定就能做到可用的詞彙比對，不必裝擴充。
"""

from __future__ import annotations

import re
import unicodedata

_CJK = r"㐀-䶿一-鿿豈-﫿"
_TOKEN_RE = re.compile(rf"[{_CJK}]+|[a-z0-9]+")
# 常見虛字：兩字皆為虛字的雙連詞丟掉，降低「的、是、嗎」這類假相似
_STOP_CHARS = set("的了嗎呢吧啊呀是在有和與及或而且就也都要會可能以其之於這那哪什麼怎麼請問我你他她們")
# 疑問字：含這些字的雙連詞只描述「怎麼問」而非「問什麼」，一律丟掉（例如「幾小」「多久」的「幾」）
_QUESTION_CHARS = set("嗎呢吧幾哪什麼怎誰呀啊")
# 領域同義詞：檢索前把口語或簡稱統一成文件常用詞（雙向對稱，文件與問題都套用）
_SYNONYMS = (
    ("照顧服務員", "照服員"),
    ("居家服務員", "居服員"),
    ("照護", "照顧"),
    ("長輩", "住民"),
    ("阿公", "住民"),
    ("阿嬤", "住民"),
    ("院民", "住民"),
    ("個案", "住民"),
    ("洗澡", "沐浴"),
    # STT 常見的同音／異寫：記錄 vs 紀錄、儲存 vs 保存（實測 whisper 會輸出「照護記錄要儲存多久」）
    ("記錄", "紀錄"),
    ("儲存", "保存"),
    ("存放", "保存"),
)

_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def normalize(text: str) -> str:
    """全形轉半形、英文小寫、壓縮空白。

    Args:
        text: 原始文字。

    Returns:
        正規化後文字。
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("臺", "台")  # 檢索時視為同字；顯示仍用原文
    for source, target in _SYNONYMS:
        text = text.replace(source, target)
    return re.sub(r"\s+", " ", text.lower()).strip()


def bigrams(text: str, drop_stop: bool = True) -> list[str]:
    """把文字切成 token：中文連續段取雙連詞、英數取整段。

    Args:
        text: 輸入文字。
        drop_stop: 是否丟掉兩字皆為虛字的雙連詞。

    Returns:
        token 清單（保留重複，供計數）。
    """
    tokens: list[str] = []
    for run in _TOKEN_RE.findall(normalize(text)):
        if run[0].isascii():
            tokens.append(run)
            continue
        if len(run) == 1:
            if not (drop_stop and run in _STOP_CHARS):
                tokens.append(run)
            continue
        for i in range(len(run) - 1):
            pair = run[i : i + 2]
            if drop_stop and (
                (pair[0] in _STOP_CHARS and pair[1] in _STOP_CHARS)
                or pair[0] in _QUESTION_CHARS
                or pair[1] in _QUESTION_CHARS
            ):
                continue
            tokens.append(pair)
    return tokens


def tsvector_source(text: str) -> str:
    """產生給 `to_tsvector('simple', …)` 的空白分隔 token 字串。"""
    return " ".join(bigrams(text))


def support_score(claim: str, evidence: str) -> float:
    """計算主張被證據文字「字面支持」的比例（主張雙連詞出現在證據中的比例）。

    這是決定性的檢核訊號，不是正確率：高分代表用字大多來自證據，
    低分代表主張可能不是從證據來的（例如模型自行補充）。

    Args:
        claim: 回答中的一句主張。
        evidence: 被引用切塊的全文。

    Returns:
        0 到 1 的比例；主張沒有可比對 token 時回傳 0。
    """
    claim_tokens = set(bigrams(claim))
    if not claim_tokens:
        return 0.0
    evidence_tokens = set(bigrams(evidence))
    return len(claim_tokens & evidence_tokens) / len(claim_tokens)


def cn_number_to_int(text: str) -> int | None:
    """把簡單中文數字（如「二十四」「七十二」「三」）或阿拉伯數字轉成整數。

    Args:
        text: 數字字串。

    Returns:
        整數；無法解析時回傳 None。
    """
    text = text.strip()
    if text.isdigit():
        return int(text)
    if not text or any(ch not in _CN_DIGITS and ch not in "十百" for ch in text):
        return None
    total, current = 0, 0
    for ch in text:
        if ch == "百":
            total += (current or 1) * 100
            current = 0
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
        else:
            current = _CN_DIGITS[ch]
    return total + current


_QUANTITY_RE = re.compile(
    r"([0-9]+|[零〇一二兩三四五六七八九十百]+)\s*(小時|個工作天|工作天|日|天|分鐘|週|個月|年|人|位|名|床)"
)


def extract_quantities(text: str) -> set[tuple[int, str]]:
    """擷取文字中的「數字＋單位」組合，用於跨文件數值衝突檢查。

    Args:
        text: 文字。

    Returns:
        (數值, 正規化單位) 的集合。
    """
    unit_map = {"天": "日", "工作天": "工作日", "個工作天": "工作日", "個月": "月"}
    found: set[tuple[int, str]] = set()
    for number_text, unit in _QUANTITY_RE.findall(normalize(text)):
        value = cn_number_to_int(number_text)
        if value is not None:
            found.add((value, unit_map.get(unit, unit)))
    return found
