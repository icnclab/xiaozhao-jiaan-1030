"""規則式去識別化。

在寫入資料庫與送進 LLM 之前執行。規則刻意保守、可稽核；
已知限制（沒有稱謂的單獨人名、外號）見 docs/data-flow.md §3，
因此不能以遮罩取代「真實資料只用機構核可服務」的要求。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.security import hmac_hex

RESIDENT = "〔個案〕"
PERSON = "〔人名〕"
ROOM = "〔房號〕"
PHONE = "〔電話〕"
ID_NO = "〔證號〕"
DATE = "〔日期〕"
CUSTOM = "〔自訂遮罩〕"

# 臺灣常見姓氏（單姓＋常見複姓），用於「姓＋稱謂」樣式
_SURNAMES = (
    "陳林黃張李王吳劉蔡楊許鄭謝洪郭邱曾廖賴徐周葉蘇莊呂江何蕭羅高潘簡朱鍾彭游詹胡施沈余盧梁趙顏柯翁魏孫戴"
    "范方宋鄧杜傅侯曹薛丁卓阮馬董温唐藍石蔣古紀姚連馮歐程湯黄田康姜白汪鄒尤巫鐘黎涂龔嚴韓袁金童陸夏柳凃邵"
)
_COMPOUND_SURNAMES = ("歐陽", "張簡", "范姜", "司馬", "諸葛", "上官", "東方")
# 強稱謂：前面可接 0–2 個名字字元（「王先生」「王大明先生」「陳阿嬤」）
_STRONG_TITLES = (
    "老先生|老太太|先生|小姐|太太|女士|阿公|阿嬤|阿媽|阿伯|阿姨|阿婆|爺爺|奶奶|伯伯|伯母|叔叔|嬸嬸"
)
# 弱稱謂：只接受「姓＋稱謂」緊鄰（「林伯」「李媽媽」「黃督導」），避免「張貼公告」這類誤遮
_WEAK_TITLES = "媽媽|爸爸|大哥|大姐|老師|護理師|督導|主任|院長|醫師|伯|嬤|姨|婆"
_SURNAME_CLASS = "".join(sorted(set(_SURNAMES)))
# 以姓氏字開頭的常用詞：遇到就不遮（「家屬許多次」「住民方便嗎」）
_COMMON_WORDS = (
    "方便", "方式", "方法", "方面", "高興", "高齡", "高度", "許多", "曾經", "何時", "何必", "何況", "金額",
    "石膏", "白天", "夏天", "程度", "童年", "古代", "連續", "連絡", "馬上", "黃色", "江湖", "施打", "周圍",
    "周邊", "游泳", "洪水", "全部", "林業", "田地", "余額", "康復", "姜汁", "蘇醒", "安全", "余下", "陸續",
    "范圍", "孫子", "孫女", "柯基", "丁點", "包括", "潘朵", "嚴重", "嚴格", "韓國", "袁區", "童話", "紀錄",
)

_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # 身分證字號 A123456789／居留證號
    (re.compile(r"\b[A-Za-z][12]\d{8}\b|\b[A-Za-z][A-Da-d89]\d{8}\b"), ID_NO, "id_number"),
    # 手機、市話
    (re.compile(r"(?<!\d)09\d{2}[-\s]?\d{3}[-\s]?\d{3}(?!\d)"), PHONE, "phone"),
    (re.compile(r"(?<!\d)0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)"), PHONE, "phone"),
    # 出生日期等完整日期（民國或西元）
    (re.compile(r"(?<!\d)(?:19|20)\d{2}[/.\-年]\d{1,2}[/.\-月]\d{1,2}日?"), DATE, "date"),
    (re.compile(r"民國\s*\d{2,3}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日"), DATE, "date"),
    # 房號／床號：「302房」「302 室」「A棟3樓302」「5床」「302-1床」
    (re.compile(r"(?<![\d.])\d{1,4}(?:-\d{1,2})?\s*(?:號房|房|室|號床|床)"), ROOM, "room"),
    (re.compile(r"(?:房號|床號|房間)\s*[:：]?\s*[A-Za-z]?\d{1,4}(?:-\d{1,2})?"), ROOM, "room"),
    # 「302 王先生」這種房號接人名：先遮房號數字（後面人名由下一條處理）
    (re.compile(r"(?<![\d.])\d{3,4}(?=\s*[" + _SURNAME_CLASS + r"])"), ROOM, "room"),
    # 複姓／單姓＋名(0-2 字)＋強稱謂
    (
        re.compile(
            r"(?:" + "|".join(_COMPOUND_SURNAMES) + r")[一-鿿]{0,2}?(?:" + _STRONG_TITLES + r")"
        ),
        RESIDENT,
        "name_title",
    ),
    (
        re.compile(r"[" + _SURNAME_CLASS + r"][一-鿿]{0,2}?(?:" + _STRONG_TITLES + r")"),
        RESIDENT,
        "name_title",
    ),
    # 姓＋弱稱謂（緊鄰）
    (re.compile(r"[" + _SURNAME_CLASS + r"](?:" + _WEAK_TITLES + r")"), RESIDENT, "name_title"),
    # 「老王說」「小林的」這類暱稱：後面須接常見虛字或標點才算
    (
        re.compile(r"(?<=[老小])[" + _SURNAME_CLASS + r"](?=[說講要想問吵他她的，。、！？\s]|$)"),
        PERSON,
        "nickname",
    ),
    # 「住民陳大明」「家屬林小美」這類角色詞＋姓名（lookbehind 各分支同為 2 字）
    (
        re.compile(r"(?<=住民|家屬|個案|長輩|病人|女兒|兒子)[" + _SURNAME_CLASS + r"][一-鿿]{1,2}"),
        PERSON,
        "role_name",
    ),
]


def _is_common_word(fragment: str) -> bool:
    return any(fragment.startswith(word) for word in _COMMON_WORDS)


@dataclass(frozen=True)
class DeidResult:
    """去識別化結果。

    Attributes:
        text: 遮罩後文字。
        hits: 各規則命中次數（只記規則名稱，不記原文）。
    """

    text: str
    hits: dict[str, int] = field(default_factory=dict)


def _mask_custom_terms(text: str, term_hmacs: set[tuple[str, int]]) -> tuple[str, int]:
    """以 HMAC 比對機構自訂遮罩詞（資料庫不存明文）。

    Args:
        text: 輸入文字。
        term_hmacs: (hmac, 長度) 集合。

    Returns:
        (遮罩後文字, 命中次數)。
    """
    if not term_hmacs:
        return text, 0
    lengths = sorted({length for _, length in term_hmacs}, reverse=True)
    hashes = {h for h, _ in term_hmacs}
    out, i, hits = [], 0, 0
    while i < len(text):
        matched = False
        for length in lengths:
            piece = text[i : i + length]
            if len(piece) == length and hmac_hex(piece, "deid") in hashes:
                out.append(CUSTOM)
                i += length
                hits += 1
                matched = True
                break
        if not matched:
            out.append(text[i])
            i += 1
    return "".join(out), hits


def deidentify(text: str, term_hmacs: set[tuple[str, int]] | None = None) -> DeidResult:
    """遮罩文字中的個資樣式。

    Args:
        text: 原始文字（可能含個資）。
        term_hmacs: 機構自訂遮罩詞的 (HMAC, 長度) 集合。

    Returns:
        遮罩結果。
    """
    hits: dict[str, int] = {}
    masked, custom_hits = _mask_custom_terms(text, term_hmacs or set())
    if custom_hits:
        hits["custom"] = custom_hits
    for pattern, replacement, name in _PATTERNS:

        def _replace(match: re.Match[str], replacement: str = replacement, name: str = name) -> str:
            if name in {"name_title", "role_name"} and _is_common_word(match.group(0)):
                return match.group(0)
            hits[name] = hits.get(name, 0) + 1
            return replacement

        masked = pattern.sub(_replace, masked)
    # 合併連續的相同遮罩標記，例如「〔房號〕〔個案〕」保留，但「〔個案〕〔個案〕」併成一個
    masked = re.sub(r"(〔[^〕]+〕)(?:\s*\1)+", r"\1", masked)
    return DeidResult(text=masked, hits=hits)


def term_hmac(term: str) -> str:
    """計算自訂遮罩詞的 HMAC（建立 deid_terms 用）。"""
    return hmac_hex(term, "deid")
