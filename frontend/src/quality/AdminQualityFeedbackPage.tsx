import { publicLabel, publicDisplayText } from '../publicText';
import { useEffect, useRef, useState } from "react";
import { useAdmin } from "../admin/AdminApp";
import { Link, useSearchParams } from "react-router-dom";
import { api, formatTime, getToken, post } from "../api";
import { ErrorBox } from "../liff/components";
import { FeedbackFields, type Correction } from "./FeedbackFields";

import { OriginalCorrection, TraceSummary, ReviewHistory, OriginalSources, errorLabel } from "./FeedbackReviewContext";

import { ReviewEvidenceFields } from "./ReviewEvidenceFields";

interface Row { gold_priority?: string; gold_readiness?: "ready" | "needs_review" | "not_eligible"; id: string; qa_id: string; status: string; revision: number; submission: Correction;
  reviewed_correction: (Correction & { evidence_checked?: boolean; reviewer_notes?: string }) | null;
  qa_snapshot: { question: string; ai_answer: string; sources: { document_title: string; locator: string; text: string; source_url: string }[]; runtime: unknown; rag_version?: string | null; qa_policy_version?: string | null };
  created_at: string; review_history?: unknown[] }
interface Legacy { id: string; qa_item_id: string; question_masked: string; status: string; kind: string }

export function AdminQualityFeedbackPage() {
  const { user } = useAdmin();
  const isAdmin = user.role === "admin";
  const [searchParams] = useSearchParams();
  const linkedFeedbackId = searchParams.get("id");
  const [goldFilter, setGoldFilter] = useState("");
  const [goldQueue, setGoldQueue] = useState(false);
  const [stats, setStats] = useState<Record<string, number>>({});
  const goldLabel = (state?: string) => state === "ready" ? "可使用" : state === "not_eligible" ? "不適用" : isAdmin ? "需要重新審核" : "需要管理員重新審核";
  const [rows, setRows] = useState<Row[]>([]);
  const [status, setStatus] = useState("pending_review");
  const [selected, setSelected] = useState<Row | null>(null);
  const [value, setValue] = useState<Correction | null>(null);
  const [checked, setChecked] = useState(false);
  const [reviewerNotes, setReviewerNotes] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [legacy, setLegacy] = useState<Legacy[] | null>(null);
  const [legacyLoading, setLegacyLoading] = useState(false);
  const request = useRef(0);
  const reviewForm = useRef<HTMLElement>(null);
  useEffect(() => {
    if (selected) reviewForm.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [selected]);
  const load = async () => {
    const seq = ++request.current;
    try {
      const query = new URLSearchParams();
      if (status) query.set("status", status);
      if (isAdmin && goldFilter) query.set("gold_readiness", goldFilter);
      if (isAdmin && goldQueue) query.set("gold_queue", "true");
      const result = await api<Row[]>(`/api/quality/feedback${query.size ? `?${query}` : ""}`);
      if (isAdmin) {
        const counts = await api<Record<string, number>>("/api/quality/gold/stats");
        if (seq === request.current) setStats(counts);
      }
      if (seq === request.current) setRows(result);
    } catch (e) { if (seq === request.current) setError(e); }
  };
  useEffect(() => { setSelected(null); setValue(null); void load(); return () => { request.current++; }; }, [status, goldFilter, goldQueue, isAdmin]);
  useEffect(() => {
    if (!linkedFeedbackId) return;
    api<Row>(`/api/quality/feedback/${linkedFeedbackId}`)
      .then(detail => { setSelected(detail); setValue(detail.reviewed_correction || detail.submission); setChecked(false); setReviewerNotes(""); })
      .catch(setError);
  }, [linkedFeedbackId]);
  const choose = async (row: Row) => {
    setBusy(true); setError(null);
    try {
      const detail = await api<Row>(`/api/quality/feedback/${row.id}`);
      setSelected(detail); setValue(detail.reviewed_correction || detail.submission);
      setChecked(false); setReviewerNotes("");
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const loadLegacy = async () => {
    setLegacyLoading(true); setError(null);
    try { setLegacy(await api<Legacy[]>("/api/admin/feedback")); }
    catch (e) { setError(e); }
    finally { setLegacyLoading(false); }
  };
  const review = async (decision: string) => {
    if (!selected || !value) return;
    setBusy(true); setError(null);
    try {
      const general = { error_type: value.error_type, expected_behavior: value.expected_behavior, correct_answer: value.correct_answer,
        correct_source_document: value.correct_source_document, correct_source_page_or_section: value.correct_source_page_or_section,
        evidence_summary: value.evidence_summary, notes: value.notes };
      const gold = isAdmin ? { ...general, evidence_checked: checked,
        evidence_basis_type: value.evidence_basis_type ?? null, policy_identifier: value.policy_identifier ?? "", policy_version: value.policy_version ?? "",
        institution_identifier: value.institution_identifier ?? "", institution_rule_identifier: value.institution_rule_identifier ?? "", expert_review_record: value.expert_review_record ?? "",
        complete_answer_confirmed: value.complete_answer_confirmed ?? false, data_quality_checked: value.data_quality_checked ?? false, data_quality_conflicts: value.data_quality_conflicts ?? "" } : general;
      await post(`/api/quality/feedback/${selected.id}/review`, { ...gold, status: decision,
        expected_revision: selected.revision, reviewer_notes: reviewerNotes });
      setSelected(null); setValue(null); await load();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const exportData = async (format: string, gold = false) => {
    setBusy(true); setError(null);
    try {
      const token = getToken();
      const response = await fetch(`/api/quality/dataset/${gold ? "gold/" : ""}export?format=${format}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!response.ok) throw { message: "匯出失敗，請確認權限或重試" };
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a"); link.href = url; link.download = `quality-${gold ? "gold" : "verified"}.${format}`;
      document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  return <div className="stack">
    <h1>回答回饋與品質審核</h1>
    <p className="muted">回饋須核對依據並驗證後，才可匯出為正式資料集。待審核與駁回資料不會匯出。</p>
    <ErrorBox error={error} />
    <div className="row"><label>狀態<select value={status} disabled={busy} onChange={e => { setGoldQueue(false); setGoldFilter(""); setStatus(e.target.value); }}>
      <option value="pending_review">待審核</option><option value="verified">已驗證</option><option value="rejected">已駁回</option><option value="">全部</option>
    </select></label><button className="btn" disabled={busy} onClick={load}>重新整理</button>
      {["json", "jsonl", "csv"].map(format => <button className="btn" key={format} disabled={busy} onClick={() => exportData(format)}>匯出已驗證 {format.toUpperCase()}</button>)}
    </div>
    {isAdmin && <section className="card stack" aria-label="標準案例資料管理"><h2>標準案例資料管理</h2>
      <div className="row">{[["pending_review", "待一般審核"], ["needs_review", "標準案例待重新審核"], ["ready", "標準案例可使用"], ["not_eligible", "標準案例不適用"]].map(([key, label]) =>
        <button className="btn" key={key} disabled={busy} onClick={() => { setGoldQueue(false); setStatus(key === "pending_review" ? key : "verified"); setGoldFilter(key === "pending_review" ? "" : key); }}>{label}：{stats[key] ?? "…"}</button>)}</div>
      <label>標準案例資料狀態<select value={goldFilter} disabled={busy} onChange={e => { setGoldQueue(false); setGoldFilter(e.target.value); if (e.target.value) setStatus("verified"); }}>
        <option value="">全部</option><option value="needs_review">需要重新審核</option><option value="ready">可使用</option><option value="not_eligible">不適用</option>
      </select></label>
      <label><input type="checkbox" checked={goldQueue} disabled={busy} onChange={e => { setGoldQueue(e.target.checked); if (e.target.checked) { setStatus("verified"); setGoldFilter("needs_review"); } else setGoldFilter(""); }} /> 只看標準案例待審核</label>
      <div className="row">{["json", "jsonl", "csv"].map(format => <button className="btn" key={format} disabled={busy} onClick={() => exportData(format, true)}>匯出正式標準案例{format.toUpperCase()}</button>)}</div></section>}
    <p className="muted">已驗證不等於可作正式標準案例；正式匯出只包含已驗證且資料資格可使用的回饋。</p>
    <table><thead><tr><th>時間</th><th>問題</th><th>錯誤類型</th><th>狀態</th><th>標準案例資料狀態</th><th /></tr></thead><tbody>
      {rows.map(row => <tr key={row.id}><td>{formatTime(row.created_at)}</td><td>{row.qa_snapshot.question}</td><td>{errorLabel((row.reviewed_correction || row.submission).error_type)}</td><td>{publicLabel(row.status)}</td><td>{goldLabel(row.gold_readiness)}{isAdmin && goldQueue && <div className="small muted">{row.gold_priority}</div>}</td>
        <td><button className="btn" disabled={busy} onClick={() => choose(row)}>檢視與審核</button></td></tr>)}
      {!rows.length && <tr><td colSpan={6}>尚無此狀態回饋</td></tr>}
    </tbody></table>
    {selected && value && <section key={selected.id} ref={reviewForm} className="card stack"
      aria-labelledby="feedback-review-heading" data-feedback-id={selected.id}
      style={{ scrollMarginTop: "calc(var(--admin-fixed-header-height, 0px) + 16px)" }}><h2 id="feedback-review-heading">原問答與修正</h2>
      <p>問：{selected.qa_snapshot.question}</p><p>原回答：{publicDisplayText(selected.qa_snapshot.ai_answer)}</p>
      <Link to={`/liff/answers/${selected.qa_id}`} target="_blank">開啟原問答</Link>
      <OriginalCorrection submission={selected.submission} />
      <p role="status">標準案例資料狀態：{goldLabel(selected.gold_readiness)}（以最近一次保存的審核為準）</p>
      {!isAdmin && <p className="muted small">標準案例資料資格由系統管理員進行最終確認。</p>}
      <h3>審核修正內容</h3>
      {isAdmin && <ReviewEvidenceFields value={value} onChange={setValue} disabled={busy} />}
      <FeedbackFields value={value} onChange={setValue} disabled={busy} reviewMode={isAdmin} />
      {isAdmin && <label><input type="checkbox" checked={checked} disabled={busy} onChange={e => setChecked(e.target.checked)} /> 我已核對正確答案／行為及原文依據</label>}
      <label>審核備註<textarea maxLength={3000} value={reviewerNotes} onChange={e => setReviewerNotes(e.target.value)} /></label>
      <div className="row"><button className="btn primary" disabled={busy || (isAdmin && !checked)} onClick={() => review("verified")}>驗證</button>
        <button className="btn" disabled={busy} onClick={() => review("rejected")}>駁回</button>
        <button className="btn" disabled={busy} onClick={() => review("pending_review")}>保留待審核</button>
        <button className="btn" disabled={busy} onClick={() => setSelected(null)}>關閉</button></div>
      <OriginalSources sources={selected.qa_snapshot.sources} />
      <TraceSummary snapshot={selected.qa_snapshot} role={user.role} />
      <ReviewHistory history={selected.review_history} />
    </section>}
    <details><summary>舊版單純回饋（不納入 已驗證資料集）</summary>
      <p className="muted">此處僅查閱舊版回饋列表，不會載入審核欄位。新版修正內容在「檢視與審核」時已自動預填。</p>
      <button className="btn" disabled={legacyLoading || legacy !== null} onClick={loadLegacy}>
        {legacyLoading ? "載入中…" : legacy !== null ? legacy.length ? "已載入" : "無舊版回饋" : "載入既有回饋"}
      </button>
      <p role="status" aria-live="polite">{legacyLoading ? "正在載入舊版回饋…" : legacy !== null ? legacy.length ? `已載入 ${legacy.length} 筆舊版回饋` : "" : ""}</p>
      {legacy?.map(row => <p key={row.id}>{row.question_masked}／{row.kind}／{publicLabel(row.status)} <Link to={`/liff/answers/${row.qa_item_id}`}>查看</Link></p>)}
    </details>
  </div>;
}
