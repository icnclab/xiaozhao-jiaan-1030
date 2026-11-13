import { useEffect, useState } from "react";
import { api } from "../../api";
import { ErrorBox } from "../../liff/components";
import { publicLabel } from "../../publicText";

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

const pct = (value: number | null) => value === null ? "尚無資料" : `${(value * 100).toFixed(1)}%`;

export function AdminMetricsPage() {
  const [days, setDays] = useState(30);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    setError(null);
    api<Metrics>(`/api/admin/metrics?days=${days}`).then(setMetrics).catch(setError);
  }, [days]);
  if (!metrics) return <div><ErrorBox error={error} />{!error && <p className="muted">資料載入中…</p>}</div>;
  const tile = (title: string, value: string, explanation: string) => <div className="card metric">
    <div className="muted small">{title}</div><div className="value">{value}</div><div className="small">{explanation}</div>
  </div>;
  return <div className="stack">
    <h1>服務品質與運作概況</h1>
    <p className="muted">先看目前需要處理的工作與服務是否正常；比例是運作觀察，不代表任何同仁犯錯。</p>
    <div className="row"><span className="muted small">統計期間</span>{[7, 30, 90].map(day =>
      <button key={day} className={`btn ${days === day ? "primary" : ""}`} onClick={() => setDays(day)}>{day} 天</button>)}</div>
    <div className="notice info small">{metrics.note}</div>
    <div className="metrics">
      {tile("待處理案件", String(metrics.backlog.pending), `另有 ${metrics.backlog.in_progress} 件處理中；${metrics.backlog.unassigned} 件尚未指派`)}
      {tile("需要確認的回答", String(metrics.feedback.wrong), `使用者回報需要確認；期間內共 ${metrics.feedback.answered} 則回答`)}
      {tile("回答是否附上來源", pct(metrics.answered.value), `${metrics.answered.numerator}／${metrics.answered.denominator} 則符合原統計定義`)}
      {tile("知識庫更新狀況", `${metrics.knowledge_base.current_documents} 份現行文件`, `最近發布：${metrics.knowledge_base.last_published_at ? new Date(metrics.knowledge_base.last_published_at).toLocaleString("zh-TW") : "尚無紀錄"}`)}
      {tile("系統運作狀態", metrics.case_create_failed.count === 0 && metrics.notifications.failed === 0 ? "正常" : "需要留意", `建案失敗 ${metrics.case_create_failed.count} 件；通知失敗 ${metrics.notifications.failed}／${metrics.notifications.total}`)}
    </div>
    <details className="card"><summary><strong>詳細報表</strong></summary><div className="metrics" style={{ marginTop: 12 }}>
      {tile("安全拒答比例", pct(metrics.refusal_rate.value), `${metrics.refusal_rate.numerator}／${metrics.refusal_rate.denominator}；安全拒答是保護機制，不代表操作錯誤`)}
      {tile("平均首次回覆時間", metrics.first_reply_minutes.mean === null ? "尚無資料" : `${metrics.first_reply_minutes.mean} 分鐘`, `中位數 ${metrics.first_reply_minutes.median ?? "尚無資料"} 分鐘；已回覆 ${metrics.first_reply_minutes.replied} 件`)}
      {tile("通知錯誤", String(metrics.notifications.failed), `總通知數 ${metrics.notifications.total}`)}
      {tile("回覆需要確認比例", pct(metrics.feedback.wrong_rate), `${metrics.feedback.wrong}／${metrics.feedback.answered}；屬品質回饋，不等同系統或人員犯錯`)}
    </div><h3>轉交／拒答原因分布</h3><table><tbody>{Object.entries(metrics.refusal_rate.by_reason).map(([key, value]) =>
      <tr key={key}><td>{publicLabel(key)}</td><td>{value}</td></tr>)}</tbody></table>
    <div className="small muted">原統計定義：{metrics.backlog.definition}；{metrics.answered.definition}；{metrics.refusal_rate.definition}</div></details>
    <p className="small muted">統計期間：{new Date(metrics.period.from).toLocaleString("zh-TW")} 至 {new Date(metrics.period.to).toLocaleString("zh-TW")}。本頁未變更後端統計定義。</p>
  </div>;
}
