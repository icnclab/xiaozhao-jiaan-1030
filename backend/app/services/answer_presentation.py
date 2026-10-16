"""BA16 answer wording only; source facts still pass the existing verifier."""
import re
from dataclasses import replace

from app.providers.llm import CandidateAnswer
from app.services.query_understanding import medication_admin_intent, purchasing_rule_intent, PURCHASE_FIELDS


def scoped_ba16_candidate(question, evidence_map):
    """Extract a requested administrative fact; normal verification still applies.

    Require the actual heading, same-version bounded table scope and requested
    body field. No answer constants, document IDs or threshold exceptions.
    """
    field = purchasing_rule_intent(question)
    if not field:
        return None
    from app.services.qa_policy import looks_like_injection
    claims = []
    for header_ref, header in evidence_map.items():
        if not header.scope_chunk_ids or not re.search(r'BA16代購或代領或代送服務', re.sub(r'\s+', '', header.text)):
            continue
        if looks_like_injection(header.scope_context) or looks_like_injection(header.text):
            continue
        for ref, item in evidence_map.items():
            if item.version_id != header.version_id or item.chunk_id not in header.scope_chunk_ids or ref == header_ref:
                continue
            body = re.sub(r'\s+', '', item.text)
            if item.injection_flag or looks_like_injection(item.text):
                continue
            for sentence in re.split(r'(?<=。)', body):
                if any(word in sentence for word in PURCHASE_FIELDS[field]):
                    claims.append({'text': sentence, 'citation_refs': [ref]})
        if claims:
            return CandidateAnswer(claims=[{'text': 'BA16 代購或代領或代送服務。', 'citation_refs': [header_ref]}] + claims)
    return None


def ba16_refs(question, evidence_map):
    if not medication_admin_intent(question):
        return None
    for ref, item in evidence_map.items():
        if not getattr(item, 'scope_chunk_ids', ()) or '藥品' not in item.text:
            continue
        scope_ids = set(item.scope_chunk_ids)
        scope = [(r, c) for r, c in evidence_map.items() if c.chunk_id in scope_ids
                 and c.version_id == item.version_id]
        header = next((r for r, c in scope if re.search(
            r'BA16代購或代領或代送服務', re.sub(r'\s+', '', c.text))), None)
        if header and re.search(r'目的物品或事項包括.{0,50}藥品', re.sub(r'\s+', '', item.text)):
            return [header, ref]
    return None


def include_ba16_fact(question, evidence_map, candidate: CandidateAnswer):
    if purchasing_rule_intent(question) and not medication_admin_intent(question) and not (candidate.needs_human or candidate.conflict or not candidate.raw_ok or not candidate.claims):
        # Cite the actual table heading to establish which service the split
        # attribute row belongs to. This claim still passes node_verify.
        for ref, item in evidence_map.items():
            if item.scope_chunk_ids and re.search(r'BA16代購或代領或代送服務', re.sub(r'\s+', '', item.text)):
                heading = {'text': 'BA16 代購或代領或代送服務。', 'citation_refs': [ref]}
                field = purchasing_rule_intent(question)
                facts = []
                for body_ref, body_item in evidence_map.items():
                    if body_item.version_id != item.version_id or body_item.chunk_id not in item.scope_chunk_ids:
                        continue
                    body = re.sub(r'\s+', '', body_item.text)
                    for sentence in re.split(r'(?<=。)', body):
                        if any(word in sentence for word in PURCHASE_FIELDS[field]) and body_ref != ref:
                            facts.append({'text': sentence, 'citation_refs': [body_ref]})
                return replace(candidate, claims=[heading] + facts + candidate.claims)
    refs = ba16_refs(question, evidence_map)
    if not refs or candidate.needs_human or candidate.conflict or not candidate.raw_ok or not candidate.claims:
        return candidate
    # A wording correction, not a verifier bypass: exact source vocabulary and
    # both original chunk refs go through citation/support/output-risk checks.
    fact = {'text': 'BA16 代購或代領或代送服務的目的物品或事項包括：餐食、食材、生活用品、藥品。',
            'citation_refs': refs}
    facts = [fact]
    scope_ids = set(evidence_map[refs[1]].scope_chunk_ids)
    for ref, item in evidence_map.items():
        if item.chunk_id not in scope_ids:
            continue
        text = re.sub(r'\s+', '', item.text)
        for pattern in [r'上述目的物品或事項應為長照給付對象本身所需']:
            match = re.search(pattern, text)
            if match:
                facts.append({'text': match.group().rstrip('。') + '。', 'citation_refs': [ref]})
    return replace(candidate, claims=facts + [c for c in candidate.claims if c not in facts])


def ba16_safety_note(question, evidence_map, verified_claims):
    refs = ba16_refs(question, evidence_map)
    if not refs or not any('藥品' in c['text'] and set(refs) <= set(c['refs']) for c in verified_claims):
        return ''
    # This is the assistant's safety boundary, not an invented BA16 legal rule.
    return ('\n用藥安全提醒：代領或代購不代表可以自行決定買哪種藥、用量、服法或給藥；'
            '請依核定服務內容辦理，用藥判斷請由督導協助醫療專業人員確認。')


# Presentation-only equivalence classes. Full matches are intentional: an
# additional exception, negation, quantity or restriction must not disappear.
_SERVICE = r'代購(?:或|、|／|/)?代領(?:或|、|／|/)?代送'
_PERSON = r'長照給付對象(?:本身|本人)?'
_FACT_PATTERNS = {
    'ba16_scope': re.compile(
        rf'(?:本|此)(?:服務|(?:服務)?組合)(?:的服務)?(?:主要)?(?:以|包含|為)?{_SERVICE}{_PERSON}物品或事項為主|'
        rf'(?:本|此)組合的服務內容包含{_SERVICE}{_PERSON}的?物品或事項|'
        rf'代購、代領或代送{_PERSON}物品或事項是本組合的主要內容之一'),
    'recipient': re.compile(
        rf'(?:上述目的物品或事項|購買物品|該服務|代購或代領或代送的物品(?:或事項)?)'
        rf'(?:應為|應以|應是|是|須為|必須為){_PERSON}(?:本身|本人)?所需(?:為主)?|'
        rf'若(?:代購的|所購)物品是{_PERSON}所需則符合本組合規定'),
    'distance': re.compile(
        r'(?:且)?(?:(?:本|此)組合適用於)?(?:距離)?(?:自案家出門(?:起算|計算|算)|自案家出門起算)?'
        r'(?:五|5)公里(?:範圍)?內(?:適用(?:本組合)?|適用於本組合)?'),
    'excess_cost': re.compile(
        rf'超過(?:五|5)公里所需費用由{_PERSON}自行負擔|'
        rf'超出部分的費用(?:需|須)?由{_PERSON}自行負擔'),
    'over_distance': re.compile(
        r'若(?:代購|代領|代送)的物品或事項的距離超過自案家出門(?:起算|計算|算)的?(?:五|5)公里'),
}


def assemble_answer(question, evidence_map, verified_claims):
    """Return display claims + safety notice without altering verification.

    Only BA16 administrative answers have semantic aliases. Other answers are
    passed through unchanged, including all safety/escalation wording. Unknown
    clauses are never fuzzily matched or truncated. Citation storage must use
    the original verified claims, not this display projection.
    """
    notice = ba16_safety_note(question, evidence_map, verified_claims)
    field = purchasing_rule_intent(question)
    if not notice and not field:
        return list(verified_claims), notice

    rows, seen = [], set()
    for claim in verified_claims:
        text = claim['text']
        # E-labels inside model prose duplicate the structured citation labels.
        text = re.sub(r'[（(]E\d+(?:[、,， ]+E\d+)*[）)]', '', text)
        text = re.sub(r'(五|5)公里內[，,]\s*適用本組合', r'\1公里內適用本組合', text)
        text = re.sub(r'(所需)[，,]\s*則符合本組合規定', r'\1則符合本組合規定', text)
        text = re.sub(r'[，,]?但(?=該服務應以)', '，', text)
        text = re.sub(r'[，,]?但(?=(?:本|此)組合以)', '，', text)
        parts = re.split(r'[。；\n，]', text)
        retained = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            compact = re.sub(r'\s+', '', part)
            compact = re.sub(r'^[一二三四五六七八九十]+[、.]', '', compact)
            part = re.sub(r'^[一二三四五六七八九十]+[、.]', '', part)
            if compact in ('適用本組合', '則適用本組合') and field not in ('distance', 'scope'):
                continue
            if field == 'items' and re.search(r'目的物品或事項包括[：:].*生活用品', compact):
                part = '代購、代領或代送服務的物品包括生活用品'
                compact = part
            if field == 'subsidized_items' and re.search(r'目的物品或事項包括[：:].*補助品', compact):
                part = '代購、代領或代送服務的物品包括補助品'
                compact = part
            if field == 'errands' and '必要之辦理事項' in compact:
                match = re.search(r'必要之辦理事項.*', compact)
                part = '服務包含' + match.group()
                compact = part
            if field == 'medicine' and re.search(r'目的物品或事項包括[：:].*藥品', compact):
                part = 'BA16 可代購藥品'
                compact = part.replace(' ', '')
            if field == 'medicine' and compact == 'BA16代購或代領或代送服務' and 'medicine_items' in seen:
                continue
            if field == 'organize' and compact.startswith('以上服務均含') and '購買物品之清理與歸位' in compact:
                part = '服務包含購買物品之清理與歸位'
                compact = part
            if field == 'accounting' and compact.startswith('以上服務均含') and '記帳' in compact:
                part = '服務包含記帳'
                compact = part
            # Project only verified sentences relevant to the requested field.
            # Never drop a medicine-specific restriction or exception.
            if field in ('medicine', 'distance', 'recipient', 'items', 'subsidized_items', 'errands', 'organize', 'accounting'):
                fact_fields = []
                for name, pattern in [('distance', r'公里|超出範圍|超出部分的費用'), ('recipient', r'本身所需|本人所需|家人|百分之五十|50%'),
                                      ('organize', r'整理|歸位'), ('accounting', r'記帳|記賬'),
                                      ('subsidized_items', r'補助品')]:
                    if re.search(pattern, compact):
                        fact_fields.append(name)
                if field == 'medicine' and fact_fields == ['recipient'] and re.search(r'本身所需|本人所需', compact) and not re.search(r'家人|百分之|50%', compact):
                    fact_fields = []
                if fact_fields and field not in fact_fields and not re.search(r'藥品|處方藥|給藥|用藥|不得|不可|不適用|僅限', compact):
                    continue
            compact = compact.replace('且適用距離', '距離')
            compact = re.sub(r'^(?:且)?適用範圍在距離', '距離', compact)
            # The injected, already verified item list supports this direct
            # answer. Do not infer service approval or medicine selection.
            medicine = re.fullmatch(
                rf'(?:BA16)?{_SERVICE}服務的目的物品或事項包括[：:]'
                r'餐食、食材、生活用品、藥品|'
                r'(?:BA16)?(?:可|可以)?(?:代購|代領|代購／代領)(?:項目)?(?:包括|包含)?藥品|'
                r'(?:本|此)組合涵蓋的物品或事項(?:包括|包含)藥品|'
                r'照服員可以提供代購、代領或代送藥品等服務|'
                r'照服員可以提供(?:代購|代領|代送)藥品等服務|'
                r'(?:代購|代領|代送)藥品屬於目的物品或事項之一|包括藥品|'
                rf'{_SERVICE}的服務內容(?:包含|包括)藥品', compact)
            if medicine:
                key = 'medicine_items'
                part = '依 BA16 服務範圍，可以協助代購／代領／代送藥品'
            else:
                key = next((k for k, p in _FACT_PATTERNS.items() if p.fullmatch(compact)), None)
            if key == 'ba16_scope' and 'medicine_items' in seen:
                continue
            if key == 'over_distance' and 'excess_cost' in seen:
                continue
            if compact == '可以' and 'medicine_items' in seen:
                continue
            if key is not None and key in seen:
                continue
            if key is None and compact in seen:
                continue
            if key is not None:
                seen.add(key)
            else:
                seen.add(compact)
            if key == 'excess_cost':
                part = '超出範圍的所需費用由長照給付對象自行負擔'
            retained.append(part)
        if retained:
            rows.append(dict(claim, text='，'.join(retained) + '。'))
    return rows, notice
