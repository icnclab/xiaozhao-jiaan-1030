"""Conservative checks for requested facts that lexical support alone cannot establish."""
from __future__ import annotations

import re

from app.services.text import bigrams, normalize

_PENALTY = re.compile(r"罰|扣薪|扣款|扣錢")
_MONETARY_PENALTY = re.compile(r"罰款|罰鍰|罰金|罰錢|扣薪|扣款|扣錢|罰.{0,4}(?:多少錢|多少元|幾元|幾塊)")
_AMOUNT_REQUEST = re.compile(r"多少|幾|金額|上限|下限|最[多少高低]")
_MONEY = re.compile(r"(?:\d[\d,]*(?:\.\d+)?|[零〇一二兩三四五六七八九十百千萬億]+)\s*(?:億|萬|千|百)?\s*元")
_GENERIC = set(bigrams("罰款 罰鍰 罰金 金額 多少錢 多少元 幾元 幾塊 處罰 罰錢 扣薪 扣款 扣錢 最少 最多 最低 最高 一次 上限 下限"))


# 評鑑／評核「規則」可以回答，但不能把規則當成特定機構的實際結果預測。
_EVALUATION_CONTEXT = re.compile(r"評鑑|評核|考核")
_EVALUATION_RESULT = re.compile(
    r"(?:幾|多少)\s*分"
    r"|(?:拿|得)\s*[A-EＡ-Ｅ](?!\d)"
    r"|通過|合格|不合格"
)
_EVALUATION_PREDICTION = re.compile(
    r"一定|會不會|是否會|會拿|能拿|可能|大概|預測|預估|今年|本次|這次"
)
_EVALUATION_RULE = re.compile(
    r"評分標準|評分方式|怎麼計分|如何計分"
    r"|(?:幾|多少)\s*分\s*算"
    r"|每項.{0,8}(?:幾|多少)\s*分"
    r"|未出席.{0,12}(?:怎麼評|如何評)"
)


def asks_evaluation_outcome_prediction(question: str) -> bool:
    """辨識對特定機構實際評鑑結果的預測，而非詢問評分規則。

    例如：
    - 「今年評鑑一定會拿幾分？」 -> True
    - 「這次評鑑會通過嗎？」 -> True
    - 「評鑑每項怎麼計分？」 -> False
    - 「業務負責人未出席，A1 怎麼評？」 -> False
    """
    question = normalize(question)

    if not _EVALUATION_CONTEXT.search(question):
        return False

    if _EVALUATION_RULE.search(question):
        return False

    return bool(
        _EVALUATION_RESULT.search(question)
        and _EVALUATION_PREDICTION.search(question)
    )


def asks_penalty_amount(question: str) -> bool:
    """Recognize a requested monetary sanction, independent of any particular question."""
    question = normalize(question)
    return bool(_MONETARY_PENALTY.search(question) and _AMOUNT_REQUEST.search(question))


def supported_penalty_amounts(question: str, evidence: str) -> set[str]:
    """Require a monetary sanction and topic overlap in the same sentence.

    Join layout line breaks, but never borrow money from another sentence or chunk.
    A score such as E, a meeting interval, or a fee elsewhere is not a fine amount.
    This is a necessary fact check, not a substitute for the existing verification.
    """
    topic = set(bigrams(question)) - _GENERIC
    amounts: set[str] = set()
    for sentence in re.split(r"[。；;！？!?]", normalize(evidence).replace("\n", " ")):
        if not _PENALTY.search(sentence):
            continue
        if topic and not topic.intersection(bigrams(sentence)):
            continue
        amounts.update(re.sub(r"[\s,]", "", match.group()) for match in _MONEY.finditer(sentence))
    return amounts


def answers_supported_penalty_amount(question: str, answer: str, evidence: str) -> bool:
    """Reject off-target or invented monetary answers even when word support is high."""
    supported = supported_penalty_amounts(question, evidence)
    answer = normalize(answer)
    answered = {re.sub(r"[\s,]", "", m.group()) for m in _MONEY.finditer(answer)} if _PENALTY.search(answer) else set()
    return bool(answered) and answered <= supported
