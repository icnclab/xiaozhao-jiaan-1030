import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage, getToken, post } from "../../api";
import { ErrorBox } from "../../liff/components";
import { useAdmin } from "../AdminApp";

const FEEDBACK_SOURCE_RE = /quality-feedback-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i;

function SourceCell({ source }: { source: string | null }) {
  if (!source) return <span className="tag warn">待補</span>;
  const match = source.match(FEEDBACK_SOURCE_RE);
  if (!match) return <>{source}</>;
  return <>{source} <Link to={`/admin/feedback?id=${match[1]}`}>（查看來源品質回饋審核紀錄）</Link></>;
}

interface Version {
  id: string; version_label: string; status: string; effective_from: string | null; effective_to: string | null;
  source: string | null; source_url: string | null; file_name: string; mime: string; chunk_count: number; warnings: string[];
  parse_error: string | null; missing_fields: string[]; uploaded_at: string; published_at: string | null; is_current: boolean;
  official_source?: { title: string; official_url: string; verified: boolean } | null;
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

  const viewSavedFile = async (version: Version) => {
    setError(null);
    if (version.mime?.includes("wordprocessingml.document")) {
      return api<Version>(`/api/admin/versions/${version.id}`).then(setPreview).catch(setError);
    }
    try {
      const token = getToken();
      const response = await fetch(`/api/admin/versions/${version.id}/file`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}, cache: "no-store",
      });
      if (!response.ok) throw new Error("file_open_failed");
      const url = URL.createObjectURL(await response.blob());
      const opened = window.open(url, "_blank", "noopener,noreferrer");
      if (!opened) throw new Error("popup_blocked");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) { setError(e); }
  };

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
      <p className="muted">查看AI回答所使用的文件、保存版本與來源狀態。官方來源尚未完成核對時會明確標示「待確認」。</p>
      <ErrorBox error={error} />
      {msg && <div className="notice ok">{msg}</div>}
      <details className="card stack">
        <summary><strong>建立待審草稿</strong></summary>
        <p className="small muted">督導、主任與管理員可建立本機構草稿並上傳；上傳不會發布或進入正式 RAG。全機構共用文件仍僅限管理員建立。</p>
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="card stack" style={{ flex: 1, minWidth: 300 }}>
          <h3>1. 建立文件</h3>
          <label>文件正式名稱（必填）<input type="text" placeholder="請填完整正式名稱" value={newDoc.title} onChange={(e) => setNewDoc({ ...newDoc, title: e.target.value })} /></label>
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
          <h3>2. 上傳文件版本</h3>
          <p className="small muted">每次內容或生效日期改變都應建立新版本，不要覆蓋既有歷史版本。支援 PDF、DOCX、UTF-8 TXT。</p>
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
          <label>官方來源網址（選填）<input type="url" placeholder="僅填已核對且與本文件完全相符的政府官方網址" value={upload.url} onChange={(e) => setUpload({ ...upload, url: e.target.value })} /></label>
          <input type="file" accept=".pdf,.docx,.txt" onChange={(e) => setUpload({ ...upload, file: e.target.files?.[0] ?? null })} />
          <button className="btn primary" disabled={busy || !upload.file || !upload.docId || !upload.label} onClick={uploadVersion}>{busy ? "上傳與建立草稿中…" : "上傳為待審草稿"}</button>
        </div>
      </div></details>
      {!docs.length && <div className="card"><h3>尚未建立文件</h3><p className="muted">請先使用上方「建立文件」，再上傳第一個版本。若只是查閱既有引用，不需要建立重複文件。</p></div>}
      {docs.map((d) => {
        const current = d.versions.find((v) => v.is_current) ?? d.versions[0];
        return <div key={d.id} className="card stack document-card">
          <div className="row document-heading">
            <h3>{d.title}</h3>
            <span className="tag">{TYPES[d.doc_type] ?? "其他"}</span>
            {current && <span className={`tag ${current.status === "published" ? "ok" : "warn"}`}>{STATUS[current.status] ?? "處理中"}</span>}
          </div>
          <dl className="document-summary small">
            <dt>發布機關或來源</dt><dd>{current?.source ? <SourceCell source={current.source} /> : "尚待補充"}</dd>
            <dt>生效日期或版本日期</dt><dd>{current?.effective_from ?? current?.uploaded_at?.slice(0, 10) ?? "尚待補充"}</dd>
            <dt>官方來源</dt><dd>{current?.official_source?.verified ? <a href={current.official_source.official_url} target="_blank" rel="noopener noreferrer">查看官方原文</a> : <span className="tag warn">待確認</span>}</dd>
          </dl>
          {current && <button className="btn" onClick={() => void viewSavedFile(current)}>查看文件</button>}
          {user.role === "admin" && <details>
            <summary>管理操作與進階資訊</summary>
            {d.versions.map((v) => <div key={v.id} className="card stack small">
              <div><strong>{v.is_current ? "現行版本" : "歷史版本"}</strong>　{STATUS[v.status] ?? v.status}</div>
              <div>技術版號：{v.version_label}　檔案：{v.file_name}　切塊：{v.chunk_count}</div>
              {v.warnings.map((w) => <div key={w} className="muted">{w}</div>)}
              <div className="row">
                <button className="btn" onClick={() => void viewSavedFile(v)}>查看保存內容</button>
                {v.status === "review" && <button className="btn" onClick={() => {
                  const from = window.prompt("生效日（YYYY-MM-DD）", v.effective_from ?? "");
                  if (from === null) return;
                  const source = window.prompt("來源說明", v.source ?? "");
                  if (source === null) return;
                  void run(() => api(`/api/admin/versions/${v.id}`, { method: "PATCH", body: JSON.stringify({ effective_from: from || null, source }) }), "已更新文件資訊");
                }}>補充文件資訊</button>}
                {v.status === "review" && <button className="btn primary" disabled={busy} onClick={() => window.confirm(`發布「${d.title}」？發布後AI將可引用此內容。`) && run(() => post(`/api/admin/versions/${v.id}/publish`, {}), "已發布")}>發布</button>}
                {(v.status === "published" || v.status === "review") && <button className="btn danger" disabled={busy} onClick={() => window.confirm("停用後不再被檢索，歷史引用仍保留。確定？") && run(() => post(`/api/admin/versions/${v.id}/deactivate`, {}), "已停用")}>停用</button>}
              </div>
            </div>)}
          </details>}
        </div>;
      })}
      {preview && (
        <div className="card stack">
          <div className="row"><h3>文件內容</h3><button className="btn" onClick={() => setPreview(null)}>關閉</button></div>
          <div className="small">系統保存版本：{preview.effective_from ?? preview.uploaded_at.slice(0, 10)}　來源：{preview.source ?? "尚待補充"}　官方原文：{preview.official_source?.verified ? <a href={preview.official_source.official_url} target="_blank" rel="noopener noreferrer">查看官方原文</a> : <span className="tag warn">待確認</span>}</div>
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
