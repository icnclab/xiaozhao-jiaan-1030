import { publicLabel } from '../../publicText';
import { useEffect, useState } from "react";
import { api } from "../../api";
import { ErrorBox } from "../../liff/components";

interface Metrics {
  period: { days: number; from: string; to: string };
  refusal_rate: { value: number | null; numerator: number; denominator: number; definition: string; by_reason: Record<string, number> };
  answered: { value: number | null; numerator: number; denominator: number; definition: string };
  case_create_failed: { count: number; definition: string };
  backlog: { pending: number; in_progress: number; unassigned: number; definition: string };
  first_reply_minutes: { median: number | null; mean: number | null; replied: number; created: number; definition: string };
  feedback: { wrong: number; helpful: number; answered: number; wrong_rate: number | null; definition: string };
  notifications: { failed: number; total: number; definition: string };
  knowledge_base: { current_documents: number; last_published_at: string | null };
  note: string;
}

const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);

export function AdminMetricsPage() {
  const [days, setDays] = useState(30);
  const [m, setM] = useState<Metrics | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    api<Metrics>(`/api/admin/metrics?days=${days}`).then(setM).catch(setError);
  }, [days]);
  if (!m) return <div><ErrorBox error={error} />{!error && <p className="muted">載入中…</p>}</div>;
  const tile = (title: string, value: string, sub: string, def: string) => (
    <div className="card metric">
      <div className="muted small">{title}</div>
      <div className="value">{value}</div>
      <div className="small">{sub}</div>
      <div className="def">{def}</div>
    </div>
  );
  return (
    <div className="stack">
      <h1>治理指標</h1>
      <div className="row">
        <span className="muted small">期間</span>
        {[7, 30, 90].map((d) => <button key={d} className={`btn ${days === d ? "primary" : ""}`} onClick={() => setDays(d)}>{d} 天</button>)}
      </div>
      <div className="notice info small">{m.note}</div>
      <div className="metrics">
        {tile("拒答（轉督導）比例", pct(m.refusal_rate.value), `${m.refusal_rate.numerator} ／ ${m.refusal_rate.denominator} 題`, m.refusal_rate.definition)}
        {tile("附出處回答比例", pct(m.answered.value), `${m.answered.numerator} ／ ${m.answered.denominator} 題`, m.answered.definition)}
        {tile("建案失敗（需重試）", String(m.case_create_failed.count), "件", m.case_create_failed.definition)}
        {tile("待處理量", `${m.backlog.pending} ／ ${m.backlog.in_progress}`, `待處理／處理中；未指派 ${m.backlog.unassigned}`, m.backlog.definition)}
        {tile("首次回覆時間（中位數）", m.first_reply_minutes.median === null ? "—" : `${m.first_reply_minutes.median} 分`, `已回覆 ${m.first_reply_minutes.replied} ／ 建立 ${m.first_reply_minutes.created} 件；平均 ${m.first_reply_minutes.mean ?? "—"} 分`, m.first_reply_minutes.definition)}
        {tile("「回答有誤」比例", pct(m.feedback.wrong_rate), `${m.feedback.wrong} ／ ${m.feedback.answered} 則回答；有幫助 ${m.feedback.helpful}`, m.feedback.definition)}
        {tile("通知失敗", `${m.notifications.failed} ／ ${m.notifications.total}`, "件", m.notifications.definition)}
        {tile("知識庫", `${m.knowledge_base.current_documents} 份現行文件`, `最近發布 ${m.knowledge_base.last_published_at ? new Date(m.knowledge_base.last_published_at).toLocaleString("zh-TW") : "—"}`, "目前對本機構生效的文件版本數（含共用文件）")}
      </div>
      <div className="card">
        <h3>轉督導原因分布</h3>
        <table><tbody>{Object.entries(m.refusal_rate.by_reason).map(([k, v]) => <tr key={publicLabel(k)}><td>{publicLabel(k)}</td><td>{v}</td></tr>)}</tbody></table>
      </div>
      <p className="small muted">期間：{new Date(m.period.from).toLocaleString("zh-TW")} ～ {new Date(m.period.to).toLocaleString("zh-TW")}。這些是流程指標，不是回答正確率；引用正確性需人工抽查（docs/eval-citation-review.csv）。</p>
    </div>
  );
}
