"""Public wording never falls back to internal identifiers or exception text."""
SYSTEM_FAILURE = '系統目前無法完成回答，請稍後再試或送交督導確認'
import re

def safe_error_message(message):
    text = str(message or '')
    if not re.search(r'[\u3400-\u9fff]', text) or re.search(
        r'traceback|exception|sqlalchemy|psycopg|DB\s+error|error\s+code|Python|internal rule id|\b\w+_\w+\b', text, re.I):
        return SYSTEM_FAILURE
    return text

RISK_LABELS = {
    'emergency': '緊急安全風險', 'clinical': '需要醫療專業判斷的情況',
    'medication': '用藥安全', 'medication_selection': '用藥安全',
    'subsidy_amount': '補助或費用確認', 'respiratory_abnormality': '呼吸異常',
    'consciousness_abnormality': '意識狀態異常', 'fall_head_impact': '跌倒或頭部碰撞風險',
    'sudden_neurologic_abnormality': '突發身體異常',
    'abnormal_vomiting_or_intake': '異常嘔吐或攝取不足', 'environmental_safety': '環境安全風險',
}

def escalation_message(code):
    if code.startswith('risk_'):
        label = RISK_LABELS.get(code[5:], '安全風險')
        text = f'這個問題涉及{label}，請先通知督導確認。'
        if code in ('risk_emergency', 'risk_respiratory_abnormality', 'risk_consciousness_abnormality', 'risk_sudden_neurologic_abnormality'):
            text += '若有立即危險，請立即聯絡緊急救護。'
        return text
    if code in ('need_context', 'clarification'):
        return '請補充目前發生的情況，以及想確認的事項。'
    if code in ('llm_error', 'llm_format', 'internal_error'):
        return SYSTEM_FAILURE
    return '目前找不到足夠的規範依據，請送交督導確認。'
