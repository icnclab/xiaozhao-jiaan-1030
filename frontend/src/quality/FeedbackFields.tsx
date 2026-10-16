import { publicDisplayText } from '../publicText';
export const ERROR_TYPES = [
  ["wrong_answer", "答案錯誤"], ["incomplete_answer", "回答不完整"], ["false_refusal", "應答卻拒答"],
  ["unsafe_answer", "不安全回答"], ["retrieval_miss", "未找到相關資料"], ["wrong_source", "來源錯誤"],
  ["insufficient_evidence", "證據不足"], ["risk_false_negative", "漏攔風險"], ["risk_false_positive", "誤攔風險"],
  ["wrong_escalation", "轉人工錯誤"], ["other", "其他"],
  ["repetitive_answer", "回答內容重複"], ["verbose_answer", "回答過度冗長"], ["duplicate_citation", "引用重複"],
] as const;
export const BEHAVIORS = [["answer", "依據回答"], ["refuse", "拒答"], ["clarify", "追問"], ["escalate", "轉人工"], ["risk_block", "風險攔截"],
  ["direct_answer", "應直接回答"], ["concise_answer", "應簡潔回答"]] as const;
export interface Correction {
  evidence_basis_type?: string | null; policy_identifier?: string; policy_version?: string;
  institution_identifier?: string; institution_rule_identifier?: string; expert_review_record?: string;
  complete_answer_confirmed?: boolean; data_quality_checked?: boolean; data_quality_conflicts?: string;
  error_type: string; expected_behavior: string; correct_answer: string;
  correct_source_document: string; correct_source_page_or_section: string; evidence_summary: string; notes: string;
}
export const emptyCorrection = (): Correction => ({ error_type: "wrong_answer", expected_behavior: "answer",
  correct_answer: "", correct_source_document: "", correct_source_page_or_section: "", evidence_summary: "", notes: "" });

export function FeedbackFields({ value, onChange, disabled = false, reviewMode = false }: { reviewMode?: boolean; value: Correction; onChange: (v: Correction) => void; disabled?: boolean }) {
  const update = (key: keyof Correction, text: string) => onChange({ ...value, [key]: text });
  return <fieldset disabled={disabled} className="stack" style={{ minWidth: 0 }}>
    <legend>修正內容</legend>
    <label>錯誤類型<select value={value.error_type} onChange={e => update("error_type", e.target.value)}>
      {ERROR_TYPES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
    </select></label>
    <label>預期行為<select value={value.expected_behavior} onChange={e => update("expected_behavior", e.target.value)}>
      {BEHAVIORS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
    </select></label>
    <label>建議正確答案<textarea maxLength={6000} value={publicDisplayText(value.correct_answer)} onChange={e => update("correct_answer", e.target.value)} /></label>
    {(!reviewMode || !value.evidence_basis_type || value.evidence_basis_type === "official_kb_document") && <><label>正確來源文件<input type="text" style={{ display: "block", width: "100%", maxWidth: "100%", minWidth: 0 }} maxLength={500} value={publicDisplayText(value.correct_source_document)} onChange={e => update("correct_source_document", e.target.value)} /></label>
    <label>頁碼／章節<input type="text" style={{ display: "block", width: "100%", maxWidth: "100%", minWidth: 0 }} maxLength={500} value={publicDisplayText(value.correct_source_page_or_section)} onChange={e => update("correct_source_page_or_section", e.target.value)} /></label></>}
    <label>依據摘要<textarea maxLength={6000} value={publicDisplayText(value.evidence_summary)} onChange={e => update("evidence_summary", e.target.value)} /></label>
    <label>補充說明<textarea maxLength={3000} value={publicDisplayText(value.notes)} onChange={e => update("notes", e.target.value)} /></label>
    <p className="muted small">請用「長輩」「家屬」代稱，避免填入姓名、房號或其他個人資料。不確定正確答案或來源時可留白，由審核者確認。</p>
  </fieldset>;
}
