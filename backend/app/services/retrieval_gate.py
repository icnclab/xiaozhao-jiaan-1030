"""Evidence admission, independent of ranking bonuses and answer verification.

A pass means relevant evidence may be shown to the LLM, never that an answer is
correct. Original risk screen and post-generation verification remain mandatory.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.services.qa_policy import QaPolicy, looks_like_injection
from app.services.retrieval import RetrievedChunk, _PERMISSION_RE, _topic_match, _topic_token_groups
from app.services.text import bigrams, normalize
from app.services.evidence_text import substantive_body
from app.services.care_query import care_reporting, reporting_duty, meal_cough
from app.services.query_understanding import medication_admin_intent, purchasing_rule_intent, PURCHASE_FIELDS
from app.services.query_understanding import permission_intent, reporting_intent, boundary_intent, boundary_support, title_token_groups, clarification_reason, record_intent, record_support

# A scope label alone is not a rule. Both a normative predicate and a scope
# concept must occur in the SAME bounded body sentence as the question's topic.
_NORMATIVE = re.compile(r"可包含|不宜|不得|不可以|不可|應|須|僅|得由|得執行|得申報|可以|尚無不可|難謂|尚難|限於|禁止|受.{0,30}規範|符合|具備")
_SCOPE = re.compile(
    r"業務(?:範圍|內容|行為)|服務(?:範疇|範圍|契約|所含)|服務.{0,12}(?:包含|包括)|工作範圍|角色界線|資格|許可|認證|登錄|申報|"
    r"醫療(?:專業判斷|輔助行為|行為)|護理行為|專業法規|"
    r"(?:執行|從事|提供).{0,25}(?:服務|人員)|(?:人員|服務員).{0,25}(?:執行|從事|提供)"
)
@dataclass(frozen=True)
class GateDecision:
    admitted: bool
    route: str
    permission_intent: bool
    hybrid: float
    coverage: float
    vector: float
    title_topic: float
    body_topic: float
    rule_topic: float
    rule_excerpt: str
    reason: str
    normalized_coverage: float = 0.0
    normalized_hybrid: float = 0.0
    reporting_intent: bool = False
    procedure_topic: float = 0.0
    procedure_excerpt: str = ''

    def audit(self) -> dict:
        return asdict(self)


def assess_evidence(question: str, chunk: RetrievedChunk, policy: QaPolicy, *, check_injection: bool = True) -> GateDecision:
    """Never use combined/title_bonus/intent_bonus as admission confidence."""
    groups = _topic_token_groups(question)
    body = substantive_body(chunk.text)
    title_topic = _topic_match(title_token_groups(question), set(bigrams(chunk.title)))
    body_topic = _topic_match(groups, set(bigrams(body)))
    permission = permission_intent(question)
    reporting = reporting_intent(question)
    hybrid = policy.lexical_weight * chunk.coverage + (1 - policy.lexical_weight) * max(chunk.vector, 0)
    rule_topic, excerpt = 0.0, ''
    procedure_topic, procedure_excerpt = 0.0, ''
    for sentence in re.split(r'[。！？!?；;]', body):
        # No cross-sentence or unlimited cross-paragraph topic/rule stitching.
        for start in range(0, len(sentence), 160):
            window = sentence[start:start + 320]
            score = _topic_match(groups, set(bigrams(window)))
            if _NORMATIVE.search(window) and _SCOPE.search(window) and score > rule_topic:
                rule_topic, excerpt = score, window
            if reporting and score > procedure_topic and re.search(r'應|須|請|不得|即可|通報|報告', window) and re.search(r'通報|回報|報告|報知', window):
                procedure_topic, procedure_excerpt = score, window
    base = hybrid >= policy.min_combined and (chunk.coverage >= policy.min_top_coverage or chunk.vector >= policy.min_gate_vector)
    normalized_hybrid = policy.lexical_weight * chunk.normalized_coverage + (1 - policy.lexical_weight) * max(chunk.vector, 0)
    normalized_base = (normalized_hybrid >= policy.min_combined and chunk.normalized_coverage >= policy.min_top_coverage
                       and body_topic >= policy.min_gate_body_topic)
    # For ordinary questions keep the calibrated lexical body channel: verified
    # original coverage plus cleaned body topic coverage must BOTH meet its
    # existing threshold. Vector-only and the new title route need stronger
    # cleaned body relevance. This avoids penalizing long colloquial questions
    # merely because their unexpanded topic tokens include conversational text.
    lexical_body = (not permission and chunk.coverage >= policy.min_top_coverage
                    and body_topic >= policy.min_top_coverage)
    substantive = bool(groups) and (body_topic >= policy.min_gate_body_topic or lexical_body)
    permission_rule = rule_topic >= policy.min_gate_rule_topic
    # The new route is conjunctive: title LOCATES, topical rule text SUPPORTS.
    located_rule = title_topic >= policy.min_gate_title_topic and substantive and permission_rule
    care_duty = care_reporting(question) and reporting_duty(body, records=bool(re.search(r'紀錄|記錄', question)))
    scope = re.sub(r'\s+', '', chunk.scope_context)
    admin_scope = (medication_admin_intent(question) and permission and not boundary_intent(question)
                   and bool(chunk.scope_chunk_ids) and '藥品' in body
                   and bool(re.search(r'BA\d{2}代購.{0,12}代領.{0,12}代送', scope))
                   and bool(re.search(r'目的物品.{0,30}包括.{0,50}藥品', scope)))
    purchase_field = purchasing_rule_intent(question)
    purchase_scope = bool(chunk.scope_chunk_ids) and bool(re.search(r'BA16代購.{0,12}代領.{0,12}代送', scope))
    field_supported = purchase_field and any(word in re.sub(r'\s+', '', body) for word in PURCHASE_FIELDS[purchase_field])
    if check_injection and (chunk.injection_flag or looks_like_injection(chunk.text)):
        admitted, route, reason = False, 'reject', 'injection'
    elif clarification_reason(question):
        admitted, route, reason = False, 'reject', 'needs_clarification'
    elif purchasing_rule_intent(question) == 'distance' and not re.search(r'距離.{0,30}公里', body):
        admitted, route, reason = False, 'reject', 'purchasing_distance_missing'
    elif purchasing_rule_intent(question) == 'recipient' and not re.search(r'本身所需|本人所需|家人物品', body):
        admitted, route, reason = False, 'reject', 'purchasing_recipient_missing'
    elif purchase_field and purchase_field != 'medicine' and not field_supported:
        admitted, route, reason = False, 'reject', 'purchasing_field_missing'
    elif meal_cough(question) and not reporting:
        # Retrieval can find a procedure without establishing its clinical applicability.
        admitted, route, reason = False, 'reject', 'clinical_context_not_established'
    elif admin_scope and not looks_like_injection(chunk.scope_context):
        admitted, route, reason = True, 'administrative_scope_table', 'explicit_medication_purchase_scope'
    elif purchase_field and purchase_scope and field_supported and (base or normalized_base) and not looks_like_injection(chunk.scope_context):
        admitted, route, reason = True, 'purchasing_scope_table', 'explicit_purchasing_field'
    elif care_duty:
        admitted, route, reason = True, 'frontline_reporting_duty', 'explicit_frontline_reporting_duty'
    elif medication_admin_intent(question) and re.search(r'餐食|食材|午餐', body) and not re.search(r'藥品|成藥|買藥|領藥', body):
        admitted, route, reason = False, 'reject', 'food_purchase_not_medication_scope'
    elif record_intent(question) and not record_support(body):
        admitted, route, reason = False, 'reject', 'record_evidence_missing'
    elif not substantive:
        admitted, route, reason = False, 'reject', 'body_topic_missing'
    elif reporting and procedure_topic < policy.min_gate_rule_topic:
        admitted, route, reason = False, 'reject', 'reporting_rule_missing'
    elif permission and boundary_intent(question) and re.search(r'BA\d{2}', body, re.I) and not re.search(r'BA\d{2}', question, re.I):
        admitted, route, reason = False, 'reject', 'specific_service_scope_not_requested'
    elif permission and boundary_intent(question) and not boundary_support(excerpt):
        admitted, route, reason = False, 'reject', 'service_boundary_rule_missing'
    elif permission and not permission_rule:
        admitted, route, reason = False, 'reject', 'permission_rule_missing'
    elif base:
        admitted, route, reason = True, 'body_hybrid', 'body_relevant_and_base_signal'
    elif normalized_base:
        admitted, route, reason = True, 'normalized_body_hybrid', 'normalized_body_lexical_signal'
    elif permission and located_rule:
        admitted, route, reason = True, 'located_permission_rule', 'title_locates_body_rule'
    else:
        admitted, route, reason = False, 'reject', 'base_signal_insufficient'
    return GateDecision(admitted, route, permission, round(hybrid, 4), chunk.coverage,
                        chunk.vector, round(title_topic, 4), round(body_topic, 4),
                        round(rule_topic, 4), excerpt[:320], reason, chunk.normalized_coverage,
                        round(normalized_hybrid, 4), reporting, round(procedure_topic, 4), procedure_excerpt[:320])
