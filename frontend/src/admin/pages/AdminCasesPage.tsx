import { publicLabel } from '../../publicText';
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
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
  // 首頁統計方塊可能帶 ?status=...&mine=true&unassigned=true 連結過來；只在第一次掛載時讀取。
  const [initialParams] = useSearchParams();
  const [status, setStatus] = useState(initialParams.get("status") ?? "pending,in_progress");
  const [mine, setMine] = useState(initialParams.get("mine") === "true");
  const [unassigned, setUnassigned] = useState(initialParams.get("unassigned") === "true");
  const [includeTest, setIncludeTest] = useState(false);
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const filteredRows = rows.filter(r => (!from || r.created_at.slice(0,10) >= from) && (!to || r.created_at.slice(0,10) <= to));
  const requestId = useRef(0);
  const load = useCallback(() => {
    const currentRequest = ++requestId.current;
    setRows([]);
    setError(null);
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (mine) params.set("mine", "true");
    if (unassigned) params.set("assignee_id", "none");
    params.set("include_test", String(includeTest));
    if (q) params.set("q", q);
    api<Row[]>(`/api/admin/cases?${params}`, { cache: "no-store" }).then((result) => {
      if (currentRequest === requestId.current) setRows(result);
    }).catch((err) => {
      if (currentRequest === requestId.current) setError(err);
    });
  }, [status, mine, unassigned, q, includeTest]);
  useEffect(() => {
    load();
    return () => { ++requestId.current; };
  }, [load]);
  return (
    <div className="stack">
      <h1>案件查詢與處理</h1>
      <p className="notice info">預設顯示目前狀態為待處理或處理中的同機構案件。「只看指派給我」會排除未指派案件。日期僅篩選目前載入的最近 200 筆。
        　<a href="/api/jiaan1030/emergency-ui" className="small">🚨 緊急通報／督導接手（獨立於此處的待確認案件）</a>
      </p>

      <div className="card toolbar">
        <div className="toolbar-row">
          <div className="field">
            <label htmlFor="case-status">案件狀態</label>
            <select id="case-status" aria-label="案件狀態" value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: "auto" }}>
              <option value="pending,in_progress">待處理＋處理中</option>
              <option value="pending">待處理</option>
              <option value="in_progress">處理中</option>
              <option value="replied">已回覆</option>
              <option value="closed">已結案</option>
              <option value="">全部</option>
            </select>
          </div>
          <label className="checkline"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> 只看指派給我</label>
          <label className="checkline"><input type="checkbox" checked={unassigned} onChange={(e) => setUnassigned(e.target.checked)} /> 只看未指派</label>
          <label className="checkline"><input type="checkbox" checked={includeTest} onChange={(e) => setIncludeTest(e.target.checked)} /> 包含測試帳號建立的案件</label>
        </div>
        <div className="toolbar-row">
          <div className="field grow">
            <label htmlFor="case-search">搜尋</label>
            <input id="case-search" type="text" aria-label="搜尋案件" placeholder="搜尋待確認案件編號或內容" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="case-from">開始日期</label>
            <input id="case-from" aria-label="開始日期" type="date" value={from} onChange={e=>setFrom(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="case-to">結束日期</label>
            <input id="case-to" aria-label="結束日期" type="date" value={to} onChange={e=>setTo(e.target.value)} />
          </div>
          <button className="btn primary" onClick={load}>重新整理</button>
        </div>
      </div>

      {includeTest && <p className="notice info">已包含「由 test_ 帳號建立」的案件；這是建立者帳號標記，與是否屬於嘉安機構是兩個不同條件。其他篩選仍然有效。</p>}
      {includeTest && <button className="btn" onClick={() => { setMine(false); setUnassigned(false); setStatus(""); setQ(""); setFrom(""); setTo(""); }}>重設其他篩選（含測試帳號案件）</button>}
      <ErrorBox error={error} />
      {!error && filteredRows.length === 0 && <p role="status">目前條件沒有案件。請確認指派、狀態與日期；提問紀錄和待確認案件是不同資料。</p>}
      {from && to && from > to && <p className="notice danger" role="alert">開始日期不能晚於結束日期，請重新選擇。</p>}
      <div className="table-scroll">
        <table className="cases-table">
          <thead><tr><th>待確認案件編號</th><th>狀態</th><th>來源</th><th>分類</th><th>摘要（已去識別化）</th><th>提交人</th><th>督導</th><th>建立</th></tr></thead>
          <tbody>
            {filteredRows.map((r) => (
              <tr key={r.id}>
                <td><Link className="case-number" to={`/admin/cases/${r.id}`}>{r.number}</Link>{r.is_test && <div><span className="tag" title="由 test_ 帳號建立，不代表個案不屬於嘉安機構">測試帳號建立</span></div>}</td>
                <td><span className={`tag ${r.status === "replied" ? "ok" : r.status === "closed" ? "" : "warn"}`}>{r.status_label}</span></td>
                <td>{r.source_label}</td>
                <td>{r.category ?? "—"}</td>
                <td className="col-summary">{r.summary_masked}<div className="small muted">{publicLabel(r.reason)}</div></td>
                <td>{r.creator}</td>
                <td>{r.assignee ?? <span className="tag danger">未指派</span>}</td>
                <td>{formatTime(r.created_at)}</td>
              </tr>
            ))}
            {filteredRows.length === 0 && <tr><td colSpan={8} className="muted">沒有符合的案件</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
