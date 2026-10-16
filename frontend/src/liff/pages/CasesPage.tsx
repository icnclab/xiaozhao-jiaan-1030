import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatTime } from "../../api";
import { ErrorBox } from "../components";

interface CaseRow {
  id: string;
  number: string;
  status: string;
  status_label: string;
  summary_masked: string;
  created_at: string;
  updated_at: string;
  has_reply: boolean;
}

export function CasesPage() {
  const [rows, setRows] = useState<CaseRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    api<CaseRow[]>("/api/cases/mine").then(setRows).catch(setError);
  }, []);
  return (
    <div className="page stack">
      <h1>我的案件</h1>
      <ErrorBox error={error} />
      {rows?.length === 0 && <p className="muted">還沒有案件。</p>}
      {rows?.map((c) => (
        <Link key={c.id} to={`/liff/cases/${c.id}`} className="card" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="row">
            <strong>{c.number}</strong>
            <span className={`tag ${c.status === "replied" ? "ok" : c.status === "closed" ? "" : "warn"}`}>{c.status_label}</span>
          </div>
          <p className="small">{c.summary_masked}</p>
          <p className="muted small">更新 {formatTime(c.updated_at)}</p>
        </Link>
      ))}
    </div>
  );
}
