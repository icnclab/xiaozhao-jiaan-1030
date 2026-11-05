"""問答政策：檢索與驗證門檻、風險篩檢規則、提示注入偵測。

版本字串記在每一筆問答上。門檻是內部分流用，不是正確率，也不顯示給使用者。
初始值為開發期預設，校準紀錄見 docs/progress.md 與 docs/eval-results.md。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RiskRule:
    """風險篩檢規則：命中即轉人工。"""

    code: str
    label: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class ClarificationRule:
    """Versioned missing-context policy, evaluated after risk screening."""

    code: str
    label: str
    pattern: re.Pattern[str]
    concrete_action: re.Pattern[str]
    prompt: str


CLARIFICATION_POLICY_VERSION = '2026-10-11.clarification.1'
CLARIFICATION_RULES: tuple[ClarificationRule, ...] = (
    ClarificationRule(
        code='unspecified_repeated_operation',
        label='未說明具體服務或操作',
        pattern=re.compile(r'這樣做|以前都這樣|照以前做|(?:還是)?照原本做|照(?:原本|以前)(?:的)?(?:方式|做法)|照做'),
        # Actors (家屬/照服員) and generic words (服務/操作) do not identify
        # the requested activity. Require a named activity or action + object.
        concrete_action=re.compile(
            r'洗澡|沐浴|擦澡|餵食|餵飯|吃飯|進食|買藥|代購|代領|領藥|'
            r'翻身|拍背|移位|扶起|攙扶|換藥|抽痰|量血壓|測血糖|'
            r'推輪椅|穿衣|脫衣|剪指甲|刷牙|口腔清潔|如廁|上廁所|運動|復健|'
            r'(?:更換|換)(?:尿布|衣服|床單|敷料)|(?:清潔|清洗|打掃)(?:傷口|地板|房間|浴室)|'
            r'(?:煮|做|準備)(?:飯|早餐|午餐|晚餐|餐食)|(?:陪同|協助)(?:散步|外出|就醫|購物)|'
            r'(?:購買|買)(?:菜|餐食|食材|生活用品)|服務紀錄|通報|回報|報告督導'),
        prompt='目前還不知道你指的是哪一項服務或操作，請先說明家屬希望照服員做什麼，再依相關規範確認。',
    ),
)


@dataclass(frozen=True)
class QaPolicy:
    """問答政策。

    Attributes:
        version: 政策版本（記錄在 qa_items.qa_policy_version）。
        top_k: 送進生成的證據數。
        candidate_k: 檢索候選數。
        lexical_weight: 混合分數中字面覆蓋率的權重。
        min_top_coverage: 第一名證據的問題雙連詞覆蓋率下限（低於則視為無依據）。
        min_combined: evidence gate 的原始 hybrid 下限（不含 ranking bonus）。
        min_evidence_score: 已通過 gate 的其他證據納入排序分數下限。
        min_support: 每句主張對所引切塊的字面支持度下限。
    """

    # 2026-09-11.2：min_top_coverage 0.30→0.35（合成評測：可答題最低 0.38、無依據誤中 0.32；樣本小、邊界薄）
    # 2026-10-06.1：新增罰款／扣款金額的證據充分性檢核；所有數值門檻不變。
    version: str = "2026-10-11.gold-batch1.1"
    safety_version: str = "2026-10-11.safety-coverage.2"
    clarification_version: str = CLARIFICATION_POLICY_VERSION
    clarification_rules: tuple[ClarificationRule, ...] = CLARIFICATION_RULES
    top_k: int = 5
    candidate_k: int = 50
    lexical_weight: float = 0.55
    min_top_coverage: float = 0.18
    min_combined: float = 0.24
    min_evidence_score: float = 0.16
    min_support: float = 0.45
    # Evidence admission signals, separate from ranking bonuses. Existing
    # coverage/hybrid/vector thresholds are not lowered.
    min_gate_vector: float = 0.52
    min_gate_body_topic: float = 0.50
    min_gate_title_topic: float = 0.80
    min_gate_rule_topic: float = 0.80
    risk_rules: tuple[RiskRule, ...] = field(default_factory=tuple)


# Selection intent is distinct from administrative purchasing/collection.
# Keep its shared pattern in medication as well so the existing risk_medication
# route remains the first matched medication reason.
MEDICATION_SELECTION_PATTERN = (
    r'(?:買|選|挑)(?:哪(?:一)?種|什麼).{0,10}藥|'
    r'哪(?:一)?種.{0,8}藥.{0,8}(?:適合|合適)|'
    r'(?:幫|替).{0,8}(?:選|挑)藥|藥局.{0,6}買哪(?:一)?種|'
    r'買.{0,10}藥.{0,16}(?:買|選|挑)?哪(?:一)?種'
)

RISK_RULES: tuple[RiskRule, ...] = (
    RiskRule(
        "emergency",
        "可能是緊急狀況",
        re.compile(r"(昏倒|昏迷|不省人事|沒有?呼吸|沒有?心跳|大量出血|抽搐|胸痛|噎住|呼吸困難|意識不清|叫不醒)"),
    ),
    RiskRule(
        "clinical",
        "涉及臨床判斷",
        re.compile(
            r"(診斷|病情|是不是(中風|骨折|感染|失智|肺炎)|要不要(送醫|就醫|看醫生|叫救護車)|該不該(送醫|就醫)|"
            r"發燒.{0,6}(怎麼辦|處理|要不要)|血壓.{0,4}(多少|太高|太低|正常)|血糖.{0,4}(多少|太高|太低)|"
            r"傷口.{0,4}(感染|化膿|發炎)|褥瘡.{0,4}(怎麼|如何)(處理|治療)|嗆到|(?:一直|持續|反覆|常常|經常|容易|常)嗆|嗆咳|吞嚥困難|吞不下去|噎到)|"
            r"(?:不是|不會是|不算|排除).{0,4}(?:肺炎|感染|骨折|中風|低血糖)"
        ),
    ),
    RiskRule(
        "medication",
        "涉及用藥建議",
        re.compile(
            r"((給|餵|吃|服|用)(幾|多少)(顆|錠|粒|毫升|cc|c\.c\.)|劑量|藥量|能不能(吃|服用|使用).{0,6}藥|"
            r"要不要(吃|給|餵).{0,4}藥|停藥|加藥|減藥|藥.{0,4}(副作用|交互作用)|"
            r"藥.{0,14}(給|餵|讓|吃|服用|使用).{0,8}(長輩|住民|個案|吃|服用)|"
            r"(?:可以|能不能|可不可以|是否可以).{0,4}(?:多給|多吃|多餵).{0,6}(?:藥|一次)|"
            r"(安眠藥|止痛藥|退燒藥).{0,6}(可以|能不能|要不要)|"
            r"(給|讓).{0,4}(吃|服|用).{0,6}(半|[一二三四五六七八九十]|\d+).{0,2}(顆|錠|粒).{0,8}藥)|"
            + MEDICATION_SELECTION_PATTERN
        ),
    ),
    RiskRule(
        "subsidy_amount",
        "涉及補助或費用金額",
        re.compile(r"(補助|給付|費用|自付額).{0,6}(多少|幾元|幾塊|金額|怎麼算)|可以(領|拿|補助|報)多少"),
    ),
    RiskRule("respiratory_abnormality", "呼吸異常／安全風險",
             re.compile(r"喘(?!息)|呼吸(?:急促|困難)")),
    RiskRule("consciousness_abnormality", "意識狀態異常／安全風險",
             re.compile(r"(?:異常)?嗜睡|叫不醒|很難叫醒|恍神|意識不清|反應異常")),
    RiskRule("fall_head_impact", "跌倒／頭部碰撞事件",
             re.compile(r"跌倒|摔倒|撞(?:到)?頭|頭部碰撞")),
    RiskRule("sudden_neurologic_abnormality", "突發身體異常／安全風險",
             re.compile(r"(?:單側|一邊|一側).{0,6}(?:無力|沒力)|(?:說|講)話.{0,8}(?:不清(?:楚)?|不太清楚)|(?:突然)?口齒不清")),
    RiskRule("abnormal_vomiting_or_intake", "突發身體異常／安全風險",
             re.compile(
                 r"異常嘔吐物|咖啡色.{0,12}(?:嘔吐物|嘔吐|吐)|(?:嘔吐|吐).{0,35}咖啡色|"
                 r"(?=.*(?:幾乎.{0,5}(?:沒|沒有).{0,3}(?:喝水|飲水)|(?:喝水|飲水).{0,8}(?:明顯減少|很少|減少|少)))"
                 r"(?=.*(?:嘴(?:巴)?(?:很)?乾|精神(?:狀態)?(?:很差|變差|差|改變)|沒精神))")),
    RiskRule("medication_selection", "涉及用藥建議",
             re.compile(MEDICATION_SELECTION_PATTERN)),
    RiskRule("environmental_safety", "環境危險／安全風險",
             re.compile(
                 r'(?=.*(?:地板|地面)(?:很|太|有(?:一)?點|一直|還是|仍然|是)?(?:濕|滑|積水))'
                 r'(?=.*(?:長輩|阿公|阿嬤|個案|住民|服務使用者).{0,12}(?:走|移動|站|起身|行走))')),
)

# Extend families independently; retain established emergency/clinical priority.
_RISK_VARIANTS = {
    'emergency': r'胸(?:口|部).{0,4}(?:悶|痛|壓迫|不舒服)|心口.{0,3}(?:痛|悶)|吐血|嘔血|(?:沒有|摸不到|測不到)(?:脈搏|心跳)|(?:疑似|可能|好像|看起來|懷疑)(?:已經)?(?:死亡|過世)|(?:死亡|過世).{0,8}(?:怎麼辦|怎麼處理|如何通報)|(?:失去|無)(?:生命跡象|呼吸心跳)',
    'respiratory_abnormality': r'呼吸.{0,4}(?:不順|費力|很快|變快|怪怪|異常)|吸不到氣|喘不過氣|氣喘吁吁|上氣不接下氣',
    'consciousness_abnormality': r'叫.{0,3}(?:沒反應|沒有反應|不醒)|喚不醒|神智不清|神志不清|意識.{0,3}(?:模糊|異常)|反應.{0,3}(?:遲鈍|變慢|很慢)|(?:一直|異常|特別).{0,2}想睡|昏昏沉沉',
    'fall_head_impact': r'摔跤|跌跤|跌落|摔下|頭.{0,4}(?:撞到|撞上|碰到)|碰.{0,2}頭|撞.{0,2}腦袋',
    'sudden_neurologic_abnormality': r'(?:突然|忽然|突發).{0,8}(?:無力|沒力|站不穩|走不穩|嘴歪|臉歪|麻木)|(?:嘴|臉).{0,3}歪|(?:半邊|一邊).{0,4}(?:無力|沒力|麻)|口齒.{0,3}(?:含糊|不清)|(?:說|講)話.{0,5}(?:怪怪|異常)',
    'abnormal_vomiting_or_intake': r'(?:吐|嘔吐).{0,10}(?:咖啡|褐色|黑色|帶血|有血)|(?:咖啡渣|褐色|黑色).{0,8}(?:吐|嘔吐)|(?:一直|反覆|不停|連續).{0,3}(?:吐|嘔吐)|(?:吐|嘔吐).{0,3}(?:幾次|好幾次|多次)|(?:整天|一整天|兩天).{0,6}(?:沒吃|沒喝|不吃不喝)|喝.{0,4}(?:就吐|都吐)',
    'medication_selection': r'(?:換|改|更換).{0,8}(?:成藥|處方藥|藥物|感冒藥)|換(?:一種|別種|個)?藥|(?:哪種|哪個|什麼|哪款).{0,6}藥.{0,6}(?:好|適合|能吃|可以吃)|(?:挑|選).{0,3}藥',
    'environmental_safety': r'瓦斯.{0,4}(?:漏|味)|聞到.{0,3}瓦斯|電線.{0,4}(?:裸露|破皮)|插座.{0,4}(?:冒煙|火花)|逃生.{0,4}(?:堵住|阻塞)|走道.{0,4}(?:堆滿|堵住)|(?=.*(?:地板|地面)(?:很|太|有(?:一)?點|是)?(?:濕|滑|積水))(?=.*(?:長輩|阿公|阿嬤|住民).{0,10}(?:還沒(?:有)?|尚未|沒有)跌倒)',
}
RISK_RULES = tuple(RiskRule(r.code, r.label, re.compile(
    '(?:' + r.pattern.pattern + ')|(?:' + _RISK_VARIANTS.get(r.code, r'(?!)') + ')')) for r in RISK_RULES)
DEFAULT_POLICY = QaPolicy(version='2026-10-12.systematic.1', safety_version='2026-10-12.safety.1', risk_rules=RISK_RULES)


def clarification_decision(question: str, policy: QaPolicy = DEFAULT_POLICY):
    """Match an operation family, then distinguish named from missing action.

    None leaves legacy clarification behavior unchanged. A matched but concrete
    question explicitly continues to RAG instead of being caught by a generic
    pointer-word heuristic.
    """
    compact = re.sub(r'\s+', '', question)
    for rule in policy.clarification_rules:
        if rule.pattern.search(compact):
            concrete = bool(rule.concrete_action.search(compact))
            return {'needed': not concrete, 'rule_code': rule.code,
                    'policy_version': policy.clarification_version,
                    'reason': rule.code if not concrete else 'concrete_action_specified',
                    'prompt': rule.prompt if not concrete else None}
    return None

# 文件中的提示注入樣式：命中的切塊不送進生成，並記入檢查結果
INJECTION_RE = re.compile(
    r"(忽略(以上|先前|之前|所有|前述)?.{0,6}(指示|規則|指令|設定)|"
    r"(系統|system)\s*(指令|提示|prompt)\s*[:：]|"
    r"你現在是|扮演.{0,6}(助理|角色)|不(需要|必|用)(附|提供|引用).{0,4}(出處|來源|引用)|"
    r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+instructions|disregard\s+.{0,20}instructions|"
    r"you\s+are\s+now|jailbreak)",
    re.IGNORECASE,
)


def screen_risk(question: str, policy: QaPolicy = DEFAULT_POLICY) -> list[RiskRule]:
    """檢查問題是否命中風險規則。

    Args:
        question: 遮罩後問題。
        policy: 政策。

    Returns:
        命中的規則清單（空表示可進入規範查詢）。
    """
    # Whitespace is a spoken pause, never a way to evade safety screening.
    compact = re.sub(r'\s+', '', question)
    matched = []
    for rule in policy.risk_rules:
        text = compact
        if rule.code == 'fall_head_impact':
            text = re.sub(r'(?:還沒(?:有)?|尚未|沒有|沒|未)(?:跌倒|摔倒|撞頭|頭部碰撞)', '', text)
            text = re.sub(r'跌倒預防(?:課程|教育|訓練)', '', text)
        if rule.pattern.search(text):
            matched.append(rule)
    return matched


def looks_like_injection(text: str) -> bool:
    """文字是否含提示注入樣式。"""
    return bool(INJECTION_RE.search(text))

