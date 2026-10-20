"""去識別化規則測試：該遮的要遮、常用詞不能誤遮。"""

from __future__ import annotations

import pytest

from app.services.deid import deidentify


@pytest.mark.parametrize(
    ("raw", "must_not_contain"),
    [
        ("302 王先生的女兒要我幫忙代購成藥", ["王先生", "302"]),
        ("照顧陳阿嬤洗澡時她跌倒了", ["陳阿嬤"]),
        ("家屬林小美說要多餵一餐", ["林小美"]),
        ("住民電話 0912-345-678 請轉告", ["0912-345-678"]),
        ("身分證 A123456789 過期", ["A123456789"]),
        ("5床的李伯伯晚上不睡", ["李伯伯", "5床"]),
        ("黃督導今天不在", ["黃督導"]),
        ("出生日期 1938/05/02", ["1938/05/02"]),
        ("老王說他不想吃", ["老王"]),
    ],
)
def test_masks_personal_data(raw: str, must_not_contain: list[str]) -> None:
    result = deidentify(raw)
    for fragment in must_not_contain:
        assert fragment not in result.text, (raw, result.text)
    assert result.hits


@pytest.mark.parametrize(
    "raw",
    [
        "家屬額外要求代購物品，機構規定可以嗎？",
        "異常事件要在幾小時內完成紀錄？",
        "張貼公告的位置有規定嗎",
        "住民方便的時候再移位可以嗎",
        "家屬許多次要求加派陪伴",
        "森林公園戶外活動要幾位照服員陪同",
        "沐浴時水溫要幾度",
        "何時要通知督導",
    ],
)
def test_keeps_ordinary_questions(raw: str) -> None:
    assert deidentify(raw).text == raw


def test_custom_terms_hmac_only() -> None:
    from app.services.deid import term_hmac

    terms = {(term_hmac("小胖伯"), 3)}
    result = deidentify("小胖伯今天不肯吃飯", terms)
    assert "小胖伯" not in result.text
    assert result.hits.get("custom") == 1
