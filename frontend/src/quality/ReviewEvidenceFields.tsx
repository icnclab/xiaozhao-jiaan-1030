import type { Correction } from "./FeedbackFields";
import { publicLabel } from '../publicText';
export const EVIDENCE_BASES = [["official_kb_document", "正式知識庫文件"], ["system_safety_policy", "系統安全政策"],
  ["institution_policy", "機構內部規範"], ["expert_review", "人工專業覆核"], ["pending_evidence", "待補依據"]] as const;
export function ReviewEvidenceFields({ value, onChange, disabled }: { value: Correction; onChange: (v: Correction) => void; disabled: boolean }) {
  const input = (key: keyof Correction, label: string) => <label>{label}<input type="text" maxLength={500} value={String(value[key] ?? "")} onChange={e => onChange({ ...value, [key]: e.target.value })} /></label>;
  return <fieldset className="stack" disabled={disabled} style={{ minWidth: 0 }}><legend>依據與標準案例資料資格</legend>
    <label>依據類型<select value={value.evidence_basis_type ?? ""} onChange={e => onChange({ ...value, evidence_basis_type: e.target.value || null })}>
      <option value="">尚未分類（需要重新審核）</option>{EVIDENCE_BASES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
    </select></label>
    {value.evidence_basis_type === "official_kb_document" && <p className="muted">請在修正內容填妥來源文件、頁碼／章節及依據摘要。</p>}
    {value.evidence_basis_type === "system_safety_policy" && <><label>政策識別／名稱<select value={value.policy_identifier ?? ''} onChange={e => onChange({ ...value, policy_identifier: e.target.value })}>
      <option value="">請選擇適用規則</option><option value="RISK_RULES">安全規則</option><option value="CLARIFICATION_RULES">澄清規則</option>
      {value.policy_identifier && !['RISK_RULES', 'CLARIFICATION_RULES'].includes(value.policy_identifier) && <option value={value.policy_identifier}>{publicLabel(value.policy_identifier)}</option>}
    </select></label>{input("policy_version", "政策版本")}<p className="muted">系統安全政策不需要 PDF 頁碼，也不是正式法規來源。請填寫依據摘要。</p></>}
    {value.evidence_basis_type === "institution_policy" && <>{input("institution_identifier", "機構識別資訊")}{input("institution_rule_identifier", "機構規範識別／版本")}</>}
    {value.evidence_basis_type === "expert_review" && <><p className="muted">覆核者與時間由本次登入審核紀錄保存；專業覆核不得冒充正式法規。</p><label>專業覆核紀錄<textarea maxLength={6000} value={value.expert_review_record ?? ""} onChange={e => onChange({ ...value, expert_review_record: e.target.value })} /></label></>}
    {value.evidence_basis_type === "pending_evidence" && <p className="muted">待補依據不得匯入正式標準案例資料集。</p>}
    <label><input type="checkbox" checked={value.complete_answer_confirmed ?? false} onChange={e => onChange({ ...value, complete_answer_confirmed: e.target.checked })} /> 已確認正確答案完整且不是編輯指令</label>
    <label><input type="checkbox" checked={value.data_quality_checked ?? false} onChange={e => onChange({ ...value, data_quality_checked: e.target.checked })} /> 已確認標籤、預期行為與答案一致且無資料品質衝突</label>
    <label>尚待解決的資料品質問題<textarea placeholder="若目前沒有待解決問題，請留白。" maxLength={3000} value={value.data_quality_conflicts ?? ""} onChange={e => onChange({ ...value, data_quality_conflicts: e.target.value })} /></label>
  </fieldset>;
}
