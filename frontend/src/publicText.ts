export const SYSTEM_FAILURE = '系統目前無法完成回答，請稍後再試或送交督導確認';
const labels: Record<string, string> = {
  fall_head_impact: '跌倒或頭部碰撞風險', environmental_safety: '環境安全風險',
  respiratory_abnormality: '呼吸異常', consciousness_abnormality: '意識狀態異常',
  sudden_neurologic_abnormality: '突發身體異常', abnormal_vomiting_or_intake: '異常嘔吐或攝取不足',
  medication_selection: '用藥安全', medication: '用藥安全', emergency: '緊急安全風險',
  clinical: '需要醫療專業判斷', subsidy_amount: '補助或費用確認',
  no_evidence: '找不到足夠資料', clarification: '需要補充說明', need_context: '需要補充說明',
  RISK_RULES: '安全規則', CLARIFICATION_RULES: '澄清規則', Gold: '標準案例',
  regression: '測試結果', proxy: '參考結果', retrieval: '參考依據', 'evidence admission': '參考依據確認',
  llm_error: '暫時無法完成回答', llm_format: '暫時無法完成回答', insufficient: '找不到足夠資料',
  citation_missing: '缺少參考依據', unsupported_claim: '回答缺少參考依據', conflict: '資料內容不一致',
  suspicious_content: '資料需要確認', output_risk: '回答涉及安全風險',
  pending_review: '待審核', verified: '已驗證', rejected: '已駁回',
  'qa_policy.py': '安全規則',
};
export function publicLabel(value: unknown): string {
  const text = String(value ?? '');
  return labels[text.replace(/^risk_(?:risk_)?/, '')] || labels[text] || (/^[a-zA-Z_][a-zA-Z_\d.-]*$/.test(text) ? '需要確認' : publicDisplayText(text) || '未記錄');
}
export function publicDisplayText(value: unknown): string {
  let text = String(value ?? '');
  if (/traceback|exception|\bDB\s+error\b|\berror\s+code\b|sqlalchemy|psycopg/i.test(text)) return SYSTEM_FAILURE;
  for (const key of Object.keys(labels).sort((a, b) => b.length - a.length)) {
    text = text.split(`risk_${key}`).join(labels[key]).split(key).join(labels[key]);
  }
  text = text.replace(/這個問題系統無法直接回答[（(]知識庫中找不到足夠依據[）)]。?/, '目前找不到足夠的規範依據，請送交督導確認。');
  text = text.replace(/這個問題系統無法直接回答[（(]([^（）()]*風險|呼吸異常|意識狀態異常|突發身體異常|用藥安全)[）)]。?/, '這個問題涉及$1，請先通知督導確認。');
  return text.replace(/\b(?:risk_)?[a-z]+(?:_[a-z]+)+\b/g, '需要確認');
}
export function publicMessage(value: unknown): string {
  const text = String(value ?? '');
  if (!text || /traceback|exception|sqlalchemy|psycopg|\bDB\s+error\b|\berror\s+code\b|Python|internal rule id|\b[A-Z_]+ERROR\b|error.code|\b(?:SELECT|INSERT|UPDATE)\b|\b\w+_\w+\b/i.test(text)) return SYSTEM_FAILURE;
  return /[\u3400-\u9fff]/.test(text) ? text : SYSTEM_FAILURE;
}
