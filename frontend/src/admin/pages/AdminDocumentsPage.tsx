import { useEffect, useState } from "react";
import { api, errorMessage, post } from "../../api";
import { ErrorBox } from "../../liff/components";
import { useAdmin } from "../AdminApp";

interface Version {
  id: string; version_label: string; status: string; effective_from: string | null; effective_to: string | null;
  source: string | null; source_url: string | null; file_name: string; chunk_count: number; warnings: string[];
  parse_error: string | null; missing_fields: string[]; uploaded_at: string; published_at: string | null; is_current: boolean;
  chunks?: { id: string; seq: number; locator: string; text: string }[];
}
interface Doc { id: string; title: string; doc_type: string; scope: string; facility_types: string[]; versions: Version[] }

const STATUS: Record<string, string> = { uploaded: "已上傳", parsing: "解析中", parse_failed: "解析失敗", review: "待檢查", published: "已發布", deactivated: "已停用" };
const TYPES: Record<string, string> = { regulation: "法規", internal_rule: "機構內規", sop: "作業程序", other: "其他" };

export function AdminDocumentsPage() {
  const { user } = useAdmin();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [preview, setPreview] = useState<Version | null>(null);
  const [newDoc, setNewDoc] = useState({ title: "", doc_type: "internal_rule", scope: "org", facility_types: ["residential"] });
  const [upload, setUpload] = useState<{ docId: string; label: string; from: string; to: string; source: string; url: string; file: File | null }>({ docId: "", label: "", from: "", to: "", source: "", url: "", file: null });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => api<Doc[]>("/api/admin/documents").then(setDocs).catch(setError);
  useEffect(() => { void load(); }, []);

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true); setError(null); setMsg(null);
    try { await fn(); setMsg(ok); await load(); } catch (e) { setError(e); } finally { setBusy(false); }
  };

  const uploadVersion = () => run(async () => {
    if (!upload.file || !upload.docId) throw new Error("請選擇文件與檔案");
    const form = new FormData();
    form.append("file", upload.file);
    form.append("version_label", upload.label);
    if (upload.from) form.append("effective_from", upload.from);
    if (upload.to) form.append("effective_to", upload.to);
    if (upload.source) form.append("source", upload.source);
    if (upload.url) form.append("source_url", upload.url);
    await api(`/api/admin/documents/${upload.docId}/versions`, { method: "POST", body: form });
    setUpload({ ...upload, label: "", file: null });
  }, "已上傳，背景解析中；解析完成後請預覽、補齊欄位再發布。");

  return (
    <div className="stack">
      <h1>知識庫文件</h1>
      <p className="muted small">上傳 → 解析切塊 → 檢查（缺生效日／來源會標「待補」）→ 授權人員發布。新版發布前不影響現行版本；歷史引用永遠回到當時版本。</p>
      <ErrorBox error={error} />
      {msg && <div className="notice ok">{msg}</div>}
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="card stack" style={{ flex: 1, minWidth: 300 }}>
          <h3>建立文件</h3>
          <input type="text" placeholder="文件名稱" value={newDoc.title} onChange={(e) => setNewDoc({ ...newDoc, title: e.target.value })} />
          <div className="row">
            <select value={newDoc.doc_type} onChange={(e) => setNewDoc({ ...newDoc, doc_type: e.target.value })} style={{ width: "auto" }}>
              {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select value={newDoc.scope} onChange={(e) => setNewDoc({ ...newDoc, scope: e.target.value })} style={{ width: "auto" }} disabled={user.role !== "admin"}>
              <option value="org">本機構</option>
              <option value="shared">全機構共用（管理員）</option>
            </select>
            <select value={newDoc.facility_types[0]} onChange={(e) => setNewDoc({ ...newDoc, facility_types: [e.target.value] })} style={{ width: "auto" }}>
              <option value="residential">住宿式</option>
              <option value="home">居家</option>
              <option value="community">社區</option>
            </select>
          </div>
          <button className="btn primary" disabled={busy || !newDoc.title.trim()} onClick={() => run(() => post("/api/admin/documents", newDoc), "文件已建立，請上傳版本。")}>建立</button>
        </div>
        <div className="card stack" style={{ flex: 1, minWidth: 300 }}>
          <h3>上傳版本（PDF／DOCX／文字檔）</h3>
          <select value={upload.docId} onChange={(e) => setUpload({ ...upload, docId: e.target.value })}>
            <option value="">選擇文件…</option>
            {docs.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
          </select>
          <input type="text" placeholder="版本標籤，例如 2026-03 版" value={upload.label} onChange={(e) => setUpload({ ...upload, label: e.target.value })} />
          <div className="row">
            <label className="small">生效日 <input type="date" value={upload.from} onChange={(e) => setUpload({ ...upload, from: e.target.value })} style={{ width: "auto" }} /></label>
            <label className="small">失效日 <input type="date" value={upload.to} onChange={(e) => setUpload({ ...upload, to: e.target.value })} style={{ width: "auto" }} /></label>
          </div>
          <input type="text" placeholder="來源說明（例如：全國法規資料庫現行條文，2026-01-01 下載）" value={upload.source} onChange={(e) => setUpload({ ...upload, source: e.target.value })} />
          <input type="text" placeholder="官方出處網址（選填，由人填寫）" value={upload.url} onChange={(e) => setUpload({ ...upload, url: e.target.value })} />
          <input type="file" accept=".pdf,.docx,.txt,.md" onChange={(e) => setUpload({ ...upload, file: e.target.files?.[0] ?? null })} />
          <button className="btn primary" disabled={busy || !upload.file || !upload.docId || !upload.label} onClick={uploadVersion}>上傳</button>
        </div>
      </div>
      {docs.map((d) => (
        <div key={d.id} className="card stack">
          <h3>{d.title} <span className="tag">{TYPES[d.doc_type]}</span> <span className="tag">{d.scope === "shared" ? "共用" : "本機構"}</span> <span className="tag">{d.facility_types.join("、")}</span></h3>
          <table>
            <thead><tr><th>版本</th><th>狀態</th><th>生效～失效</th><th>來源</th><th>切塊</th><th>待補／警告</th><th>操作</th></tr></thead>
            <tbody>
              {d.versions.map((v) => (
                <tr key={v.id}>
                  <td>{v.version_label}{v.is_current && <span className="tag ok">現行</span>}<div className="small muted">{v.file_name}</div></td>
                  <td><span className={`tag ${v.status === "published" ? "ok" : v.status === "parse_failed" ? "danger" : "warn"}`}>{STATUS[v.status] ?? v.status}</span></td>
                  <td>{v.effective_from ?? "待補"} ～ {v.effective_to ?? "—"}</td>
                  <td className="small">{v.source ?? <span className="tag warn">待補</span>}</td>
                  <td>{v.chunk_count}</td>
                  <td className="small">
                    {v.missing_fields.length > 0 && <div className="tag warn">待補：{v.missing_fields.join("、")}</div>}
                    {v.parse_error && <div style={{ color: "var(--danger)" }}>{v.parse_error}</div>}
                    {v.warnings.map((w) => <div key={w} className="muted">{w}</div>)}
                  </td>
                  <td>
                    <div className="row">
                      <button className="btn" onClick={() => api<Version>(`/api/admin/versions/${v.id}`).then(setPreview).catch(setError)}>預覽</button>
                      {(v.status === "review") && <button className="btn" onClick={() => {
                        const from = window.prompt("生效日（YYYY-MM-DD）", v.effective_from ?? "");
                        if (from === null) return;
                        const source = window.prompt("來源說明", v.source ?? "");
                        if (source === null) return;
                        void run(() => api(`/api/admin/versions/${v.id}`, { method: "PATCH", body: JSON.stringify({ effective_from: from || null, source }) }), "已更新中繼資料");
                      }}>補資料</button>}
                      {v.status === "review" && <button className="btn primary" disabled={busy} onClick={() => run(() => post(`/api/admin/versions/${v.id}/publish`, {}), "已發布")}>發布</button>}
                      {(v.status === "published" || v.status === "review") && <button className="btn danger" disabled={busy} onClick={() => window.confirm("停用後不再被檢索，歷史引用仍可查看。確定？") && run(() => post(`/api/admin/versions/${v.id}/deactivate`, {}), "已停用")}>停用</button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {preview && (
        <div className="card stack">
          <div className="row"><h3>版本預覽：{preview.version_label}</h3><button className="btn" onClick={() => setPreview(null)}>關閉</button></div>
          {preview.chunks?.map((c) => (
            <div key={c.id} className="small" style={{ borderTop: "1px solid var(--line)", padding: "6px 0" }}>
              <strong>{c.locator}</strong>
              <div style={{ whiteSpace: "pre-wrap" }}>{c.text}</div>
            </div>
          ))}
          {preview.chunks?.length === 0 && <p className="muted">{preview.parse_error ? errorMessage({ code: "x", message: preview.parse_error, retryable: false, status: 0 }) : "尚無切塊"}</p>}
        </div>
      )}
    </div>
  );
}
