import { useState } from "react";
import { formatTime } from "../api";
import { publicLabel, publicDisplayText } from '../publicText';
import { BEHAVIORS, ERROR_TYPES, type Correction } from "./FeedbackFields";

type RecordData = Record<string, unknown>;
const record = (value: unknown): RecordData => value && typeof value === "object" && !Array.isArray(value) ? value as RecordData : {};
const text = (value: unknown): string => value === null || value === undefined || value === "" ? "未記錄" : typeof value === "string" || typeof value === "number" ? String(value) : "未記錄";
export const errorLabel = (code: string) => code === "risk_false_negative" ? "漏掉風險" : ERROR_TYPES.find(([key]) => key === code)?.[1] || publicLabel(code);
const behaviorLabel = (code: string) => BEHAVIORS.find(([key]) => key === code)?.[1] || publicLabel(code);
const outcomeLabels: Record<string, string> = { answered: "回答", answer: "回答", refused: "拒答", refuse: "拒答", clarify: "追問", escalated: "轉人工", escalate: "轉人工", risk_block: "風險攔截" };
const decisionLabels: Record<string, string> = { verified: "已驗證", rejected: "已駁回", pending_review: "待審核" };

function ReadOnlyFields({ fields }: { fields: [string, string][] }) {
  return <dl className="stack" style={{ margin: 0, overflowWrap: "anywhere" }}>{fields.map(([label, value]) =>
    <div key={label}><dt><strong>{label}</strong></dt><dd style={{ margin: 0, whiteSpace: "pre-wrap" }}>{publicDisplayText(value)}</dd></div>)}</dl>;
}
export function OriginalCorrection({ submission }: { submission: Correction }) {
  const [open, setOpen] = useState(false);
  return <section className="stack" aria-label="使用者原始回饋"><h3>使用者原始回饋</h3>
    <details onToggle={e => setOpen(e.currentTarget.open)}><summary>查看完整原始回饋</summary>
      {open && <div className="stack">
        <ReadOnlyFields fields={[
          ["錯誤類型", errorLabel(submission.error_type)], ["預期行為", behaviorLabel(submission.expected_behavior)],
          ["建議正確答案", text(submission.correct_answer)], ["正確來源文件", text(submission.correct_source_document)],
          ["頁碼／章節", text(submission.correct_source_page_or_section)], ["依據摘要", text(submission.evidence_summary)], ["補充說明", text(submission.notes)],
        ]} />
      </div>}
    </details>
  </section>;
}
const reasonLabels: Record<string, string> = {
  no_evidence: "找不到足夠資料", risk_medication: "用藥安全", medication: "用藥安全", risk_false_negative: "漏掉風險",
  risk_emergency: "緊急狀況風險", emergency: "緊急狀況風險", risk_clinical: "臨床判斷風險", clinical: "臨床判斷風險",
  risk_subsidy_amount: "補助金額風險", subsidy_amount: "補助金額風險", need_context: "需要補充資訊",
  insufficient: "依據不足", conflict: "資料內容不一致", suspicious_content: "資料含可疑指令",
  llm_error: "回答產生失敗", llm_format: "回答格式異常", citation_missing: "缺少引用依據",
  output_risk: "回答含風險內容", unsupported_claim: "回答缺少依據支持",
};
export const reasonLabel = (value: unknown) => {
  const code = text(value);
  const label = reasonLabels[code] || reasonLabels[code.replace(/^risk_risk_/, "risk_")];
  return label || publicLabel(code);
};
export function TraceSummary({ snapshot }: { role?: string; snapshot: { runtime: unknown; sources: unknown[]; rag_version?: string | null; qa_policy_version?: string | null } }) {
  const runtime = record(snapshot.runtime);
  const risk = record(runtime.risk_gate_result);
  const codes = Array.isArray(risk.codes) ? risk.codes : Array.isArray(runtime.risk_gate_result) ? runtime.risk_gate_result : null;
  const result = record(runtime.escalation_result);
  const outcome = text(result.outcome);
  const riskSummary = risk.executed === false ? "未執行" : codes ? codes.length ? `命中：${codes.map(reasonLabel).join("、")}` : "未命中" : "未記錄";
  return <section className="stack" aria-label="系統處理摘要"><h3>系統處理摘要</h3>
    <ReadOnlyFields fields={[
      ["處理結果", outcomeLabels[outcome] || publicLabel(outcome)], ["轉交原因", reasonLabel(result.reason)],
      ["風險判斷", riskSummary],
    ]} />

  </section>;
}
export function ReviewHistory({ history }: { history?: unknown[] }) {
  return <section className="stack" aria-label="審核歷程"><h3>審核歷程</h3>
    {!history?.length ? <p>尚無審核紀錄</p> : <div style={{ overflowX: "auto" }}><table><thead><tr><th>時間</th><th>審核者</th><th>動作</th><th>備註</th></tr></thead>
      <tbody>{history.map((entry, index) => { const row = record(entry); const correction = record(row.correction);
        return <tr key={index}><td>{row.created_at ? formatTime(String(row.created_at)) : "未記錄"}</td>
          <td style={{ overflowWrap: "anywhere" }}>{text(row.reviewer_id)}</td><td>{decisionLabels[text(row.decision)] || text(row.decision)}</td>
          <td style={{ whiteSpace: "pre-wrap" }}>{text(correction.reviewer_notes)}</td></tr>;
      })}</tbody></table></div>}
  </section>;
}


export function OriginalSources({ sources }: { sources: { document_title: string; locator: string; text: string; source_url: string }[] }) {
  const [open, setOpen] = useState(false);
  return <section className="card stack" aria-label={`原回答引用來源（${sources.length} 筆）`}>
    <h3>原回答引用來源（{sources.length} 筆）</h3>
    <details onToggle={e => setOpen(e.currentTarget.open)}><summary>查看原回答引用</summary>
      {open && <div className="stack">
        {!sources.length && <p>原回答沒有引用來源</p>}
        {sources.map((source, index) => <article className="notice" key={index}>
          <strong>{source.document_title}／{source.locator}</strong>
          <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{source.text}</p>
          <a href={source.source_url} target="_blank" rel="noreferrer">原引用入口</a>
        </article>)}
      </div>}
    </details>
  </section>;
}
