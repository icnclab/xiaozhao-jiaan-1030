import { useEffect, useState } from "react";
import { api, post } from "../../api";
import { ErrorBox } from "../../liff/components";
import { useAdmin } from "../AdminApp";

interface Template { id?: string; text: string; is_active: boolean }
interface Cat { id: string; name: string; description: string | null; sort_order: number; is_active: boolean; default_assignee: { id: string; display_name: string } | null; templates: (Template & { id: string; sort_order: number })[] }
interface UserRow { id: string; display_name: string; role: string; is_active: boolean }

export function AdminCategoriesPage() {
  const { user } = useAdmin();
  const [cats, setCats] = useState<Cat[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [editing, setEditing] = useState<{ id: string | null; name: string; description: string; sort_order: number; is_active: boolean; default_assignee_id: string; templates: string } | null>(null);
  const canEdit = user.role === "admin";

  const load = () => api<Cat[]>("/api/admin/categories").then(setCats).catch(setError);
  useEffect(() => {
    void load();
    api<UserRow[]>("/api/admin/users").then((rows) => setUsers(rows.filter((u) => u.role !== "caregiver" && u.is_active))).catch(() => undefined);
  }, []);

  const save = async () => {
    if (!editing) return;
    const body = {
      name: editing.name, description: editing.description || null, sort_order: editing.sort_order, is_active: editing.is_active,
      default_assignee_id: editing.default_assignee_id || null,
      templates: editing.templates.split("\n").map((t) => t.trim()).filter(Boolean).map((text) => {
        const existing = cats.find((c) => c.id === editing.id)?.templates.find((t) => t.text === text);
        return { id: existing?.id, text, is_active: true };
      }),
    };
    try {
      setCats(editing.id ? await api<Cat[]>(`/api/admin/categories/${editing.id}`, { method: "PUT", body: JSON.stringify(body) }) : await post<Cat[]>("/api/admin/categories", body));
      setEditing(null);
    } catch (e) {
      setError(e);
    }
  };

  return (
    <div className="stack">
      <h1>問題分類設定</h1>
      <p className="muted small">分類與常見問題模板由此設定；預設督導決定分類回報送到誰的待處理區。{!canEdit && "（督導可檢視，修改需管理員）"}</p>
      <ErrorBox error={error} />
      {canEdit && !editing && <button className="btn primary" onClick={() => setEditing({ id: null, name: "", description: "", sort_order: cats.length, is_active: true, default_assignee_id: "", templates: "" })}>新增分類</button>}
      {editing && (
        <div className="card stack">
          <h3>{editing.id ? "編輯分類" : "新增分類"}</h3>
          <input type="text" placeholder="分類名稱" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
          <input type="text" placeholder="說明（選填）" value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
          <div className="row">
            <label className="small">排序 <input type="text" value={editing.sort_order} onChange={(e) => setEditing({ ...editing, sort_order: Number(e.target.value) || 0 })} style={{ width: 60 }} /></label>
            <label className="small"><input type="checkbox" checked={editing.is_active} onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} /> 啟用</label>
            <select value={editing.default_assignee_id} onChange={(e) => setEditing({ ...editing, default_assignee_id: e.target.value })} style={{ width: "auto" }}>
              <option value="">預設督導：無（進共用待處理區）</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
            </select>
          </div>
          <textarea placeholder="常見問題模板，一行一則" value={editing.templates} onChange={(e) => setEditing({ ...editing, templates: e.target.value })} />
          <div className="row">
            <button className="btn primary" onClick={save} disabled={!editing.name.trim()}>儲存</button>
            <button className="btn" onClick={() => setEditing(null)}>取消</button>
          </div>
        </div>
      )}
      <table>
        <thead><tr><th>排序</th><th>分類</th><th>說明</th><th>預設督導</th><th>常見問題</th><th>狀態</th><th></th></tr></thead>
        <tbody>
          {cats.map((c) => (
            <tr key={c.id}>
              <td>{c.sort_order}</td>
              <td><strong>{c.name}</strong></td>
              <td className="small">{c.description ?? ""}</td>
              <td>{c.default_assignee?.display_name ?? <span className="muted">共用</span>}</td>
              <td className="small">{c.templates.filter((t) => t.is_active).map((t) => <div key={t.id}>• {t.text}</div>)}</td>
              <td>{c.is_active ? <span className="tag ok">啟用</span> : <span className="tag">停用</span>}</td>
              <td>{canEdit && <button className="btn" onClick={() => setEditing({ id: c.id, name: c.name, description: c.description ?? "", sort_order: c.sort_order, is_active: c.is_active, default_assignee_id: c.default_assignee?.id ?? "", templates: c.templates.filter((t) => t.is_active).map((t) => t.text).join("\n") })}>編輯</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
