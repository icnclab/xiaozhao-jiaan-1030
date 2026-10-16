import { publicLabel } from '../../publicText';
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatTime } from "../../api";
import { ErrorBox } from "../../liff/components";

interface Row {
  id: string;
  number: string;
  status: string;
  status_label: string;
  source_label: string;
  category: string | null;
  reason: string;
  summary_masked: string;
  created_at: string;
  assignee: string | null;
  creator: string | null;
  is_test: boolean;
}

export function AdminCasesPage() {
  const [status, setStatus] = useState("pending,in_progress");
  const [mine, setMine] = useState(false);
  const [includeTest, setIncludeTest] = useState(false);
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<unknown>(null);
  const requestId = useRef(0);
  const load = useCallback(() => {
    const currentRequest = ++requestId.current;
    setRows([]);
    setError(null);
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (mine) params.set("mine", "true");
    params.set("include_test", String(includeTest));
    if (q) params.set("q", q);
    api<Row[]>(`/api/admin/cases?${params}`, { cache: "no-store" }).then((result) => {
      if (currentRequest === requestId.current) setRows(result);
    }).catch((err) => {
      if (currentRequest === requestId.current) setError(err);
    });
  }, [status, mine, q, includeTest]);
  useEffect(() => {
    load();
    return () => { ++requestId.current; };
  }, [load]);
  return (
    <div className="stack">
      <h1>待確認案件</h1>
      <div className="row">
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: "auto" }}>
          <option value="pending,in_progress">待處理＋處理中</option>
          <option value="pending">待處理</option>
          <option value="in_progress">處理中</option>
          <option value="replied">已回覆</option>
          <option value="closed">已結案</option>
          <option value="">全部</option>
        </select>
        <label className="row"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> 只看指派給我</label>
        <label className="row"><input type="checkbox" checked={includeTest} onChange={(e) => setIncludeTest(e.target.checked)} /> 顯示測試案件</label>
        <input type="text" placeholder="搜尋案號或內容" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 240 }} />
        <button className="btn" onClick={load}>重新整理</button>
      </div>
      <ErrorBox error={error} />
      <table>
        <thead><tr><th>案號</th><th>狀態</th><th>來源</th><th>分類</th><th>摘要（已去識別化）</th><th>提交人</th><th>督導</th><th>建立</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td><Link to={`/admin/cases/${r.id}`}>{r.number}</Link>{r.is_test && <div><span className="tag">內部測試</span></div>}</td>
              <td><span className={`tag ${r.status === "replied" ? "ok" : r.status === "closed" ? "" : "warn"}`}>{r.status_label}</span></td>
              <td>{r.source_label}</td>
              <td>{r.category ?? "—"}</td>
              <td>{r.summary_masked}<div className="small muted">{publicLabel(r.reason)}</div></td>
              <td>{r.creator}</td>
              <td>{r.assignee ?? <span className="tag danger">未指派</span>}</td>
              <td>{formatTime(r.created_at)}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={8} className="muted">沒有符合的案件</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
