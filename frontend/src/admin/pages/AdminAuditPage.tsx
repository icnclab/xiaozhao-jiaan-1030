import { useEffect, useState } from "react";
import { api } from "../../api";
import { ErrorBox } from "../../liff/components";
import { useAdmin } from "../AdminApp";

interface AuditRow {
  id: number;
  created_at: string;
  action: string;
  outcome: string | null;
  actor_role: string | null;
  actor: string | null;
  target_type: string | null;
  target_id: string | null;
  meta: Record<string, unknown>;
}

export function AdminAuditPage() {
  const { user } = useAdmin();
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [action, setAction] = useState("");
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (user.role !== "admin") return;
    const qs = action ? `?action=${encodeURIComponent(action)}` : "";
    api<AuditRow[]>(`/api/admin/audit${qs}`).then(setRows).catch(setError);
  }, [action, user.role]);

  if (user.role !== "admin") {
    return (
      <div className="stack">
        <h1>稽核紀錄</h1>
        <div className="notice warn">
          稽核紀錄目前僅限系統管理員查看（技術設定／帳號維運範疇，與主任的機構業務管理權限分開設計）。
          若業務稽核也需要主任查看，請先與嘉安確認權限範圍，再調整後端角色設定，不由前端自行放寬。
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <h1>稽核紀錄</h1>
      <p className="small muted">僅顯示本機構最近 200 筆操作紀錄；meta 內容已限制不含填寫內容或個案代稱等細節。</p>
      <div className="row">
        <input placeholder="依 action 篩選（例如 case.assign）" value={action} onChange={(e) => setAction(e.target.value)} />
      </div>
      <ErrorBox error={error} />
      {!rows ? <p className="muted">載入中…</p> : (
        <table>
          <thead>
            <tr><th>時間</th><th>操作</th><th>結果</th><th>操作者</th><th>角色</th><th>對象</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{new Date(r.created_at).toLocaleString("zh-TW")}</td>
                <td>{r.action}</td>
                <td>{r.outcome ?? "—"}</td>
                <td>{r.actor ?? "—"}</td>
                <td>{r.actor_role ?? "—"}</td>
                <td>{r.target_type ? `${r.target_type}${r.target_id ? "：" + r.target_id : ""}` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
