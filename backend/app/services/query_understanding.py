"""Conservative query concepts shared by candidates, ranking, gate and clarify.

No document IDs, answers or numeric rule values. Actor/receiver context remains
in the original question passed to risk screening and generation.
"""
from __future__ import annotations
import re
from app.services.text import bigrams, normalize
from app.services.care_query import care_reporting, report_phrase, appetite_change, meal_cough

ACTION_ALIASES = (
    ('換藥', '更換敷料'),
    ('清傷口', '清潔傷口', '清洗傷口', '傷口清潔', '傷口簡易清潔'),
    ('餵食', '進食', '吃飯', '餵飯'), ('抽痰', '抽吸'), ('洗澡', '沐浴'), ('翻身', '變換姿勢'),
    ('回報', '通報', '報告', '報知'),
    ('服務計畫外', '服務範圍外', '非服務項目', '超出服務範圍', '超過服務範圍',
     '服務界線', '角色界線', '回歸服務契約', '依據契約與工作範圍', '額外需求'),
    ('代購成藥', '代買成藥', '買成藥', '幫忙買藥', '代購藥品', '代買藥品', '買藥', '代購'),
    ('幫忙領藥', '幫長輩領藥', '代領藥品', '代領藥', '領藥', '代領'),
)
_MED_ADMIN = re.compile(r'(?:代購|代買|買|代領|領|代拿|拿|代送|送)(?:處方藥|成藥|藥品|藥)')

PURCHASE_FIELDS = {
    'distance': ('距離', '公里'),
    'recipient': ('本身所需', '本人所需', '家人物品'),
    'items': ('生活用品', '目的物品', '餐食', '食材'),
    'subsidized_items': ('補助品',),
    'errands': ('事項', '代辦'),
    'organize': ('整理', '清理', '歸位'),
    'accounting': ('記帳', '記賬'),
    'medicine': ('藥品', '處方藥'),
    'scope': ('物品', '事項'),
}


def medication_admin_intent(question: str) -> bool:
    return bool(_MED_ADMIN.search(re.sub(r'\s+', '', question)))


def purchasing_rule_intent(question: str) -> str | None:
    """Only explicit purchasing service attributes, not medicine selection.

    No answer values are inserted; aliases describe the requested rule field.
    """
    q = re.sub(r'\s+', '', question)
    # Item words alone do not turn usage/finance questions into a service scope.
    if re.search(r'沖馬桶|怎麼使用|如何使用|會計|財務|報稅|薪資', q):
        return None
    context = bool(re.search(r'BA16|代購|代買|代領|代送|幫.{0,8}(?:買|領|送|拿)|購物|買回來', q, re.I))
    if not context and not re.search(r'生活用品|衛生紙|家人(?:的)?(?:物品|東西)|補助品|代辦事項|購物後|記帳|記賬', q):
        return None
    if re.search(r'最遠|距離|幾公里|多少公里|公里範圍|[5五]公里', q):
        return 'distance'
    if re.search(r'長輩.{0,8}自己|對象.{0,8}(?:本人|本身|所需)|本人所需|本身所需|家人.{0,8}(?:物品|東西)', q):
        return 'recipient'
    if re.search(r'家人(?:的)?(?:物品|東西)', q):
        return 'recipient'
    for field, pattern in [('subsidized_items', '補助品|補助的東西'), ('organize', '整理|理好|歸位|放回'),
                           ('accounting', '記帳|記賬'), ('errands', '代辦|事項'),
                           ('medicine', '處方藥|藥品|藥'), ('items', '生活用品|衛生紙')]:
        if re.search(pattern, q):
            return field
    return 'scope' if context else None


def normalize_colloquial(question: str) -> str:
    """Keep every substantive clause, including clinical warning signs."""
    q = re.sub(r'\s+', ' ', question.strip())
    # Only remove explicit conversational fillers, never symptoms/actions.
    return re.sub(r'^(?:(?:嗯|呃|那個|我想請問|想請問)[，,：:])+', '', q)


def contextual_question(question: str, previous: str | None) -> str:
    """Only resolve an explicit administrative follow-up in the same thread."""
    q = normalize_colloquial(question)
    if re.fullmatch(r'(?:那)?可以代買嗎[？?。]?', q) and previous:
        from app.services.qa_policy import screen_risk
        if medication_admin_intent(previous) and not screen_risk(previous):
            return normalize_colloquial(previous) + '，' + q
    return q
_CONTEXT_ALIASES = (('居家喘息', '居家式喘息'),)
PERMISSION_RE = re.compile(r'可不可以|能不能|是否可以|是否能|可否|能否|可執行|能執行|可以.{0,20}[嗎麼？?]|能.{0,20}[嗎麼？?]|資格|業務範圍|業務內容|服務範圍')
_FRAME = re.compile(r'可不可以|能不能|是否可以|是否能|可否|能否|要不要|可以|可執行|能執行|符合資格|資格|業務範圍|業務內容|服務範圍|請問|幫忙|協助|這個|那個|自己|自行|幫|我|你|他|她|它|們|嗎|麼|呢')
_ACTORS = re.compile(r'照顧服務員|照服員|居服員|護理人員|護理師|住民|家屬')
_RECEIVERS = re.compile(r'居家服務督導員|居督員|督導|居督|主管')
_GENERIC_ACTION = re.compile(r'處理|處置|弄|做(?:這|那)|怎麼辦')
_POINTER = re.compile(r'這個|那個|這件|那件|這種|那種|這樣|那樣')
_BOUNDARY_RULE = re.compile(r'(?:超出|超過|非).{0,12}服務(?:範圍|項目)|額外需求|角色界線|回歸服務契約|依據契約與工作範圍')


_RECORD_INTENT = re.compile(r'要(?:記錄|紀錄|記)(?:什麼|哪些)|怎麼(?:記錄|紀錄|記)|如何(?:記錄|紀錄|記)|紀錄什麼|記錄什麼|(?:要不要|是否|需不需要|需要).{0,6}(?:記錄|紀錄)|(?:留|留下).{0,2}(?:紀錄|記錄)')

def record_intent(question: str) -> bool:
    return bool(_RECORD_INTENT.search(question))

def record_support(text: str) -> bool:
    body = normalize(re.sub(r'\s+', '', text))
    return bool(re.search(r'(?:紀錄|記錄)', body) and re.search(
        r'(?:服務|照顧|照護|家訪|電訪|指導)(?:紀錄|記錄)|(?:紀錄|記錄).{0,12}(?:內容|項目|重點|欄位|日期|時間)|(?:填寫|記載|應記|須記)', body))


def boundary_support(text: str) -> bool:
    return bool(_BOUNDARY_RULE.search(normalize(re.sub(r'\s+', '', text))))


def reporting_intent(question: str) -> bool:
    return any(word in question for word in ACTION_ALIASES[6]) or report_phrase(question)


def permission_intent(question: str) -> bool:
    # Asking WHETHER to report an incident is a reporting-duty question, not
    # permission to perform a clinical action.
    if purchasing_rule_intent(question) and not medication_admin_intent(question):
        return False  # Attribute/eligibility rules, not permission for a clinical action.
    return (bool(PERMISSION_RE.search(question)) or medication_admin_intent(question)) and not reporting_intent(question)


def boundary_intent(question: str) -> bool:
    return any(word in normalize(question) for word in ACTION_ALIASES[7])


def _legacy_topic_token_groups(question: str) -> list[tuple[set[str], ...]]:
    topic = normalize(question)
    groups = []
    for aliases in ACTION_ALIASES + _CONTEXT_ALIASES:
        if any(normalize(alias) in topic for alias in aliases):
            groups.append(tuple(set(bigrams(alias)) for alias in aliases))
            for alias in sorted(aliases, key=len, reverse=True):
                topic = topic.replace(normalize(alias), ' ')
    if groups:
        # Actors/receivers identify context, not the action being retrieved.
        # Retain them when they themselves are the topic (e.g. staffing rules).
        topic = _ACTORS.sub(' ', topic)
        topic = re.sub(r'執行|進行|做', ' ', topic)
        if reporting_intent(question):
            topic = _RECEIVERS.sub(' ', topic)
        if boundary_intent(question):
            topic = re.sub(r'叫|要求|做|的事情|事情|事項|工作', ' ', topic)
    topic = _FRAME.sub(' ', topic)
    groups.extend(({token},) for token in sorted(set(bigrams(topic))))
    return groups


def topic_token_groups(question: str) -> list[tuple[set[str], ...]]:
    if medication_admin_intent(question) and purchasing_rule_intent(question) == 'medicine':
        return [tuple(set(bigrams(alias)) for alias in ACTION_ALIASES[8] + ACTION_ALIASES[9])]
    purchase_field = purchasing_rule_intent(question)
    if purchase_field:
        field_aliases = PURCHASE_FIELDS[purchase_field]
        return [tuple(set(bigrams(word)) for word in aliases) for aliases in (
            ('代購', '代領', '代送'), field_aliases)]
    if care_reporting(question):
        return [tuple(set(bigrams(word)) for word in aliases) for aliases in (
            ('通報', '回報', '報告', '報知'), ('異常事件', '身體不適', '異常狀況'))]
    if medication_admin_intent(question):
        # Normalize only the explicit administrative action for retrieval;
        # risk screening and generation still receive the full question.
        compact = re.sub(r'\s+', '', question)
        aliases = ACTION_ALIASES[9] if re.search(r'(?:代領|領)(?:藥品|藥)', compact) else ACTION_ALIASES[8]
        return [tuple(set(bigrams(alias)) for alias in aliases)]
    # Strip complete functional phrases BEFORE removing action verbs, which
    # previously split 是否可執行 into the spurious topics 是否 / 否可.
    topic = re.sub(r'是否(?:可以|需要|能夠|可|能)?|可否|能否|否可|能不能|可不可以|應如何|如何|哪些|什麼', ' ', question)
    if record_intent(question):
        topic = _RECORD_INTENT.sub('紀錄', topic)
        topic = re.sub(r'今天|今日|長輩', ' ', topic)
        # Meal action is context for the requested service log, not techniques.
        for alias in ACTION_ALIASES[2]:
            topic = topic.replace(alias, ' ')
    topic = re.sub(r'要記', '紀錄', topic)
    topic = re.sub(r'要留', '保存', topic)
    # Context stays intact in the original question used by risk and LLM.
    # Only when an explicit report/action concept exists, avoid treating
    # contextual actors and word-boundary bigrams as additional topics.
    if reporting_intent(question):
        topic = re.sub(r'居家服務使用者|服務使用者|居家服務過程中|服務過程中|發生|事件', ' ', topic)
    return _legacy_topic_token_groups(topic)


def title_token_groups(question: str) -> list[tuple[set[str], ...]]:
    # Object-level titles may name a wound while the body names its cleaning.
    # The gate still requires the FULL cleaning action in substantive text.
    if any(word in normalize(question) for word in ACTION_ALIASES[1]):
        return [({'傷口'},)]
    return topic_token_groups(question)


def candidate_aliases(question: str) -> list[str]:
    field = purchasing_rule_intent(question)
    if field:
        return ['代購', '代領', '代送'] + list(PURCHASE_FIELDS[field])
    if care_reporting(question):
        return ['異常事件', '身體不適', '通報', '回報', '第一線服務人員', '紀錄', '記錄'] + (
            ['食慾下降', '食慾不振', '進食異常'] if appetite_change(question) else [])
    if meal_cough(question):
        return ['進食', '咳嗽', '哽傷', '哽塞', '異物', '吞嚥']
    if medication_admin_intent(question):
        return list(ACTION_ALIASES[8]) + ['藥品', '代購或代領或代送', '目的物品', '購物清單']
    # Existing expansion already covers dressing changes and other older groups.
    groups = (ACTION_ALIASES[1], ACTION_ALIASES[2], ACTION_ALIASES[6], ACTION_ALIASES[7],
              ACTION_ALIASES[8], ACTION_ALIASES[9], _CONTEXT_ALIASES[0])
    if record_intent(question):
        return ['服務紀錄', '服務記錄', '紀錄內容', '紀錄項目']
    return [word for aliases in groups if any(word in normalize(question) for word in aliases) for word in aliases]


def clarification_reason(question: str) -> str | None:
    if re.fullmatch(r'(?:那)?可以代買嗎[？?。]?', question.strip()):
        return 'unspecified_subject'
    normalized = normalize(question)
    concrete = any(normalize(word) in normalized for aliases in ACTION_ALIASES for word in aliases)
    if _POINTER.search(question) and _GENERIC_ACTION.search(question) and not concrete:
        return 'unspecified_action'
    if _POINTER.search(question) and not _legacy_topic_token_groups(question):
        return 'unspecified_subject'
    return None


def clarification_prompt(reason: str) -> str:
    if reason == 'unspecified_action':
        return '請補充你想做的具體動作，以及目前發生的情況；例如是清潔、更換用品、移動，還是其他處理？'
    return '請補充你指的是哪件事、想做什麼，或想確認哪一項規定？'
