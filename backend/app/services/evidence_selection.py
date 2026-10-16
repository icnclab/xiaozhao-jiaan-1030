"""Bounded selection of admitted chunks that answer the requested fact."""
import re
from app.services.text import bigrams, normalize, cn_number_to_int

_VALUE = re.compile(r'(?:\d+(?:\.\d+)?|[一二兩三四五六七八九十百千萬]+)\s*(?:年|月|日|天|小時|分鐘|次|人|名|元|分)|每(?:年|月|日|天|週|季)')
_TIME_VALUE = re.compile(r'(?:\d+(?:\.\d+)?|[一二兩三四五六七八九十百千萬]+)\s*(?:年|個月|月|工作天|日|天|小時|分鐘|週)')

def requested_field(question):
    q = normalize(question)
    if re.search(r'頻率|多久.{0,4}一次|每.{0,4}(多久|幾|多少)|幾次|多少次', q):
        return 'frequency'
    if re.search(r'幾年|多少年|幾天|多少天|多久|年限|期限', q):
        return 'duration'
    if re.search(r'多少|幾名|幾人|幾元|金額', q):
        return 'quantity'
    if re.search(r'重點|哪些|什麼', q) and re.search(r'記|紀錄|評估', q):
        return 'record_items'
    return None

def field_support(question, text):
    field = requested_field(question)
    q = normalize(question)
    body = normalize(re.sub(r'\s+', '', text))
    if not field:
        return 0
    # Keep value and its subject in the SAME sentence. Unrelated numbers,
    # document dates and page labels cannot fill a requested field.
    topic = set(bigrams(re.sub(r'多久|多少|幾年|幾天|幾次|幾名|幾人|幾元|年限|期限|頻率|要留|要記|重點|哪些|什麼|保存|紀錄|記錄|評估', ' ', q)))
    for sentence in re.split(r'[。；;！？!?]', body):
        if not topic.intersection(bigrams(sentence)):
            continue
        if field == 'record_items':
            action = '家訪' if '家訪' in q else '電訪' if '電訪' in q else None
            if action and action in sentence and re.search(r'紀錄.{0,8}(評估|重點)|評估重點', sentence) and re.search(r'1[.、]|一[、.]', sentence):
                return 1
        elif field == 'duration':
            if re.search(r'保存|留存|保留', q) or '要留' in question:
                if re.search(r'保存|留存|保留', sentence) and _TIME_VALUE.search(sentence):
                    return 1
            elif _TIME_VALUE.search(sentence):
                return 1
        elif field == 'frequency':
            if re.search(r'每|至少|定期|一次|次', sentence) and _VALUE.search(sentence):
                return 1
        elif _VALUE.search(sentence):
            return 1
    return 0

def prioritize_admitted(question, admitted, chosen, top_k):
    """Reserve slots for fact-bearing admitted evidence, then other admitted
    evidence. Adjacent chunks only fill leftover capacity; no top_k increase.
    """
    supported = [c for c in admitted if field_support(question, c.text)]
    if not requested_field(question):
        return chosen[:top_k], []
    ordered = supported + chosen + admitted
    result, seen = [], set()
    for c in ordered:
        if c.chunk_id not in seen:
            result.append(c); seen.add(c.chunk_id)
        if len(result) == top_k:
            break
    return result, [str(c.chunk_id) for c in supported]

def answers_requested_value(question, answer, sources):
    if requested_field(question) not in ('duration', 'frequency', 'quantity'):
        return True
    def canonical(value):
        match = re.fullmatch(r'([\d一二兩三四五六七八九十百千萬]+)\s*(.+)', value)
        if match:
            number = cn_number_to_int(match.group(1))
            if number is not None:
                return (number, match.group(2))
        return value
    pattern = _TIME_VALUE if requested_field(question) == 'duration' else _VALUE
    values = {canonical(normalize(m.group())) for m in pattern.finditer(normalize(answer))}
    supported = {canonical(normalize(m.group())) for text in sources
                 for sentence in re.split(r'[。；;！？!?]', normalize(re.sub(r'\s+', '', text)))
                 if field_support(question, sentence)
                 for m in pattern.finditer(sentence)}
    return bool(values & supported)
