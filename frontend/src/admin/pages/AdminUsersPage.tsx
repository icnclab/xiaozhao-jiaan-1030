import { useEffect, useState } from "react";
import { api, post } from "../../api";
import { ErrorBox } from "../../liff/components";
import { useAdmin } from "../AdminApp";

interface Row { id: string; username: string; original_username?: string | null; is_deleted?: boolean; display_name: string; role: string; is_active: boolean; line_bound: boolean; line_blocked: boolean }
const ROLE: Record<string, string> = { caregiver: "照服員", supervisor: "督導", director: "主任", admin: "管理員" };
// XZ_MANAGER_LINE_BINDING_20261103
// 這個函式描述的是 LINE 綁定政策本身「打算」授權誰（含主任分支），但後端
// POST .../binding-code 與 DELETE .../line-binding 目前仍只接受 supervisor/admin
// ——因為「督導/主任/管理員須真實 LINE」政策尚未經嘉安確認，兩者刻意保持分離
// （見 backend/app/api/admin_routes.py 的 SUP）。主任若在此看到可點擊按鈕但送出
// 後被 403，會誤以為系統故障；因此下方渲染另外用 canManageBindingUI 擋掉主任。
const mayManageBinding = (actor: { id: string; role: string }, target: Row): boolean => {
  if (actor.role === "admin") return true;
  if (target.role === "caregiver" && (actor.role === "supervisor" || actor.role === "director")) return true;
  if (actor.role === "director") return target.role === "supervisor" || (target.role === "director" && target.id === actor.id);
  return actor.role === "supervisor" && target.role === "supervisor" && target.id === actor.id;
};
const canManageBindingUI = (actor: { role: string }): boolean => actor.role !== "director";
const GROUPS = [
  { key: "jiaan", title: "嘉安正式帳號", label: "嘉安場測" },
  { key: "test", title: "內部測試帳號", label: "內部測試" },
  { key: "other", title: "其他帳號", label: "其他" },
];
const username = (row: Row) => row.original_username || row.username;
const group = (row: Row) => username(row).startsWith("jiaan_") ? "jiaan" : username(row).startsWith("test_") ? "test" : "other";

export function AdminUsersPage() {
  const { user } = useAdmin();
  const [rows, setRows] = useState<Row[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [code, setCode] = useState<{ user: string; code: string } | null>(null);
  const [form, setForm] = useState({ username: "", display_name: "", role: "caregiver", password: "" });
  const load = () => api<Row[]>(`/api/admin/users${showInactive ? "?include_deleted=true" : ""}`).then(setRows).catch(setError);
  const [busy, setBusy] = useState(false);
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true); setOpenMenu(null); setError(null); setCode(null);
    try { await action(); await load(); } catch (e) { setError(e); }
    finally { setBusy(false); }
  };
  useEffect(() => {
    let active = true;
    setOpenMenu(null);
    api<Row[]>(`/api/admin/users${showInactive ? "?include_deleted=true" : ""}`).then(data => { if (active) setRows(data); }).catch(e => { if (active) setError(e); });
    return () => { active = false; };
  }, [showInactive]);
  useEffect(() => { if (code) window.scrollTo({ top: 0, behavior: "smooth" }); }, [code]);
  return (
    <div className="stack">
      <h1>帳號與 LINE 綁定</h1>
      <ErrorBox error={error} />
      {code && <div className="notice ok">帳號 {code.user} 的綁定碼：<strong style={{ fontSize: 22, letterSpacing: 2 }}>{code.code}</strong>（7 天有效、只顯示這一次；請該人員本人從 LINE 官方帳號開啟 LIFF 並輸入，請勿將綁定碼貼公開群組）</div>}
      {user.role === "admin" && (
        <div className="card stack">
          <h3>新增帳號</h3>
          <div className="row">
            <input type="text" placeholder="帳號（英數）" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} style={{ width: 160 }} />
            <input type="text" placeholder="顯示名稱" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} style={{ width: 160 }} />
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} style={{ width: "auto" }}>
              {Object.entries(ROLE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            {form.role !== "caregiver" && <input type="password" placeholder="密碼（≥10 字）" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} style={{ width: 180 }} />}
            <button className="btn primary" disabled={!form.username || !form.display_name} onClick={() => post("/api/admin/users", { ...form, password: form.password || null }).then(() => { setForm({ username: "", display_name: "", role: "caregiver", password: "" }); return load(); }).catch(setError)}>新增</button>
          </div>
          <p className="small muted">照服員以 LINE 綁定登入；督導／主任／管理員後台帳密登入與本人 LINE 綁定是兩回事。緊急推播只會考慮已綁定本人 LINE 的授權人員。</p>
        </div>
      )}
      <label><input type="checkbox" checked={showInactive} onChange={e => setShowInactive(e.target.checked)} /> 顯示停用／已刪除帳號</label>
      {GROUPS.map(g => {
        const members = rows.filter(r => group(r) === g.key && (showInactive || (r.is_active && !r.is_deleted)));
        if (!members.length) return null;
        return <section key={g.key} aria-label={g.title} className="card stack">
      <h2>{g.title} <span className="tag">{g.label} · {members.length}</span></h2>
      <table>
        <thead><tr><th>帳號</th><th>名稱</th><th>角色</th><th>狀態</th><th>LINE</th><th>操作</th></tr></thead>
        <tbody>
          {members.map((r) => (
            <tr key={r.id}>
              <td>{username(r)}</td>
              <td>{r.display_name}</td>
              <td>{ROLE[r.role]}</td>
              <td><span className={`tag ${r.is_active ? "ok" : "warn"}`}>{r.is_deleted ? "已刪除" : r.is_active ? "啟用" : "停用"}</span></td>
              <td>{r.line_bound ? (r.line_blocked ? <span className="tag danger">已封鎖／取消好友</span> : <span className="tag ok">已綁定</span>) : <span className="tag warn">未綁定</span>}</td>
              <td>{r.is_deleted ? <span className="muted">歷史帳號</span> : <>
                {mayManageBinding(user, r) && canManageBindingUI(user) && <button className="btn" disabled={busy || !r.is_active || (r.role !== "caregiver" && r.line_bound)} onClick={() => void run(async () => { const c = await post<{ code: string }>(`/api/admin/users/${r.id}/binding-code`, {}); setCode({ user: r.username, code: c.code }); })}>{r.line_bound && r.role !== "caregiver" ? "已綁定 LINE" : "產生綁定碼"}</button>}
                {mayManageBinding(user, r) && !canManageBindingUI(user) && <span className="tag muted" title="督導/主任/管理員的 LINE 綁定政策尚待嘉安確認，暫不開放主任操作">待權限確認</span>}
                {(user.role === "admin" || (mayManageBinding(user, r) && r.line_bound && canManageBindingUI(user))) && <span style={{ display: "inline-block", position: "relative" }} onKeyDown={e => { if (e.key === "Escape") setOpenMenu(null); }}>
                <button className="btn" disabled={busy} aria-label={`${username(r)} 更多`} aria-expanded={openMenu === r.id} aria-controls={`account-menu-${r.id}`} onClick={() => setOpenMenu(openMenu === r.id ? null : r.id)}>更多 ▾</button>
                {openMenu === r.id && <div id={`account-menu-${r.id}`} className="card stack" style={{ minWidth: 160 }}>
                {r.line_bound && mayManageBinding(user, r) && canManageBindingUI(user) && <button className="btn danger" disabled={busy} onClick={() => window.confirm(`解除 ${r.username} 的 LINE 綁定？目前 LINE 登入及未使用綁定碼會失效，帳號與歷史資料保留。`) && void run(() => api(`/api/admin/users/${r.id}/line-binding`, { method: "DELETE" }))}>解除 LINE 綁定</button>}
                {user.role === "admin" && <button className="btn" disabled={busy} onClick={() => window.confirm(`${r.is_active ? "停用" : "啟用"} ${r.username}？${r.is_active ? "目前登入會失效，歷史資料保留。" : "需重新登入；已失效的綁定碼不會恢復。"}`) && void run(() => api(`/api/admin/users/${r.id}/active`, { method: "PATCH", body: JSON.stringify({ is_active: !r.is_active }) }))}>{r.is_active ? "停用" : "啟用"}</button>}
                {user.role === "admin" && r.id !== user.id && <button className="btn danger" disabled={busy} onClick={() => window.confirm(`刪除 ${r.username}？帳號將無法使用，LINE 綁定與登入失效；歷史案件、問答、回覆及原顯示名稱保留。原帳號名稱可重新使用，但新帳號不會承接舊資料。`) && void run(() => api(`/api/admin/users/${r.id}`, { method: "DELETE" }))}>刪除帳號</button>}
                </div>}</span>}</>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </section>;
      })}
    </div>
  );
}
