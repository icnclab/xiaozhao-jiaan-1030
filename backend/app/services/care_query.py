"""Narrow retrieval concepts; never rewrite the question used by safety checks."""
import re


def compact(text: str) -> str:
    return re.sub(r'\s+', '', text)


def meal_cough(question: str) -> bool:
    q = compact(question)
    return bool(re.search(r'吃飯|進食|吃東西|喝水|用餐', q) and re.search(r'咳|嗆', q))


def appetite_change(question: str) -> bool:
    return bool(re.search(r'不(?:太)?想吃(?:東西|飯)|不肯吃(?:東西|飯)|拒絕進食|食慾(?:下降|不振)|吃不下', compact(question)))


def report_phrase(question: str) -> bool:
    return bool(re.search(
        r'(?:跟|向)(?:單位)?(?:督導|居督|主管)(?:說|講|反映|報告|回報)|'
        r'(?:告訴|通知)(?:單位)?(?:督導|居督|主管)', compact(question)))


def care_reporting(question: str) -> bool:
    q = compact(question)
    return bool((report_phrase(q) or re.search(r'通報|回報|報告|報知', q))
                and (appetite_change(q) or re.search(r'異常(?:生理|事件|狀況)|生理.{0,4}異常|身體不適', q)))


def reporting_duty(text: str, *, records: bool = False) -> bool:
    """Explicit frontline duty in one bounded passage; symptom lists do not qualify."""
    body = compact(text)
    for start in range(0, len(body), 160):
        window = body[start:start + 320]
        if (re.search(r'異常事件|身體不適', window)
                and re.search(r'第一線服務人員|照服員|照顧服務員', window)
                and re.search(r'應立即報告.{0,8}(?:主管|居督|督導)|不得.{0,6}延遲回報', window)
                and (not records or re.search(r'完整[記紀]錄.{0,8}(?:事發|經過)', window))):
            return True
    return False
