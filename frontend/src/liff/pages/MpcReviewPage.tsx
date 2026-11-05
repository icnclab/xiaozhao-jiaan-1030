import { useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage, newRequestId, post, type Category } from "../../api";

type Segment = {
  idx: number;
  masked_text: string;
  predicted_role?: string;
  safety_flag?: string;
};
type Payload = {
  client_event_id: string;
  segments: Segment[];
  selected_idx: number[];
  summary: string;
  roles: Record<string, string>;
  [key: string]: unknown;
};
type Preview = {
  selected_segments: Segment[];
  selected_idx: number[];
  speaker_role_suggestions: Record<string, string>;
  summary_suggestion: string;
  requires_safety_review: boolean;
  emergency_candidate: boolean;
  warnings: string[];
};
type Review = {
  selected_idx: number[];
  role_corrections: Record<string, string>;
  confirmed_summary: string;
  acknowledge_review: true;
};
type Draft = {
  reviewed_summary: string;
  reviewed_roles: Record<string, string>;
  suggested_service_code: string;
  requires_supervisor_review: boolean;
  emergency_candidate: boolean;
  case_created: boolean;
  notification_sent: boolean;
  saved: boolean;
};
const roles = ["CAREGIVER", "SUPERVISOR", "FAMILY", "ELDER", "SYSTEM", "O", "UNKNOWN"];
const MAX_FILE = 500_000;

// Build a readable suggestion from confirmed, de-identified dialogue instead of
// exposing internal MPC graph labels to caregivers or supervisors.
function readableSuggestion(parts: Segment[]): string {
  const lines = parts.map(s => s.masked_text.trim()).filter(Boolean);
  return `${lines.join("；")}\n請居督依機構核准規範確認處理方式。`.slice(0, 1000);
}

const CRITICAL_FLAGS = new Set(["TIER1_SOS", "P0_EMERGENCY", "EMERGENCY"]);
function isCritical(payload: Payload | null, preview: Preview | null, draft: Draft | null): boolean {
  if (!payload) return false;
  const intents = Array.isArray(payload.active_intents) ? payload.active_intents : [];
  const slot = payload.slot_state as Record<string, unknown> | undefined;
  return Boolean(preview?.emergency_candidate || draft?.emergency_candidate ||
    intents.includes("P0_Emergency_SOS") ||
    slot?.service_domain === "SAFETY_EMERGENCY" ||
    payload.segments.some(s => CRITICAL_FLAGS.has(s.safety_flag ?? "")));
}
function hasEnvironmentRisk(payload: Payload | null): boolean {
  if (!payload) return false;
  const slot = payload.slot_state as Record<string, unknown> | undefined;
  return slot?.service_domain === "OOD_NOVEL_CRISIS" ||
    payload.segments.some(s => /淹水|咬人|犬隻|落石|道路中斷/.test(s.masked_text));
}
function hasTechnicalText(text: string): boolean {
  return /跨輪解纏結重寫|FAMILY對CAREGIVER|CAREGIVER對SYSTEM|OOD_PENDING_SOP|Thread_[0-9]+|\b(BA_22|GA09_SC09)\b/.test(text);
}


export function MpcReviewPage() {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [raw, setRaw] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [roleFixes, setRoleFixes] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState("");
  const [ack, setAck] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [submitAck, setSubmitAck] = useState(false);
  const [confirmedReview, setConfirmedReview] = useState<Review | null>(null);
  const [caseSent, setCaseSent] = useState<{id: string; number: string} | null>(null);
  const [submitRequestId, setSubmitRequestId] = useState(() => newRequestId());
  const [scenarioKeys, setScenarioKeys] = useState<string[]>([]);
  const [scenarioData, setScenarioData] = useState<Record<string, Payload>>({});
  const [scenario, setScenario] = useState("");
  const reset = () => { setCategories([]); setCategoryId(""); setSubmitAck(false); setConfirmedReview(null); setCaseSent(null); setSubmitRequestId(newRequestId()); setPayload(null); setPreview(null); setDraft(null); setSelected([]); setRoleFixes({}); setSummary(""); setAck(false); setError(""); };
  const loadData = (input: string) => {
    reset();
    try {
      const decoded: unknown = JSON.parse(input);
      if (!decoded || typeof decoded !== "object" || Array.isArray(decoded)) throw new Error("JSON 格式不正確");
      const top = decoded as Record<string, unknown>;
      if (typeof top.client_event_id === "string") {
        setScenarioKeys([]); setScenarioData({}); setScenario(""); setPayload(top as Payload);
      } else {
        const entries = Object.entries(top).filter(([, v]) => !!v && typeof v === "object" && "api_confirm_payload" in v);
        if (entries.length < 1 || entries.length > 30) throw new Error("找不到情境資料");
        const choices: Record<string, Payload> = {};
        entries.forEach(([k, v]) => { const p = (v as { api_confirm_payload?: unknown }).api_confirm_payload; if (!p || typeof p !== "object") throw new Error("缺少 payload"); choices[k] = p as Payload; });
        setScenarioData(choices); setScenarioKeys(Object.keys(choices)); setScenario(Object.keys(choices)[0]); setPayload(choices[Object.keys(choices)[0]]);
      }
    } catch (e) { setError(e instanceof Error ? e.message : "無法解析 JSON"); }
  };
  const chooseScenario = (key: string) => { reset(); setScenario(key); setPayload(scenarioData[key]); };
  const runPreview = async () => {
    if (!payload) return;
    setBusy(true); setError(""); setDraft(null); setConfirmedReview(null); setCaseSent(null); setSubmitAck(false); setCategoryId(""); setSubmitRequestId(newRequestId());
    try {
      const res = await post<Preview>("/api/mpc/preview", payload);
      setPreview(res); setSelected([...res.selected_idx]); setSummary(readableSuggestion(res.selected_segments)); setRoleFixes({}); setAck(false);
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  };
  const confirm = async () => {
    if (!payload || !preview || !ack || !summary.trim() || selected.length < 1) return;
    setBusy(true); setError("");
    const review: Review = { selected_idx: selected, role_corrections: roleFixes, confirmed_summary: summary, acknowledge_review: true };
    try {
      const result = await post<Draft>("/api/mpc/review-draft", { payload, review });
      setDraft(result); setConfirmedReview(review); setCaseSent(null); setSubmitAck(false); setSubmitRequestId(newRequestId());
      if (!result.emergency_candidate) {
        const cats = await api<Category[]>("/api/categories");
        setCategories(cats); setCategoryId("");
      }
    }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  };
  const sendCase = async () => {
    if (!draft || !payload || !confirmedReview || !submitAck || !categoryId || caseSent || busy) return;
    if (isCritical(payload, preview, draft)) { setError("這是 P0 緊急候選，禁止由一般督導案件送出；請依現場應變流程求援。"); return; }
    const text = draft.reviewed_summary.trim();
    if (!text || text.length > 1000) { setError("案件摘要不可空白，且最多 1000 字。請先精簡草稿內容。"); return; }
    if (hasTechnicalText(text)) {
      setError("請先將摘要的技術標籤改為照服員與居督看得懂的事件事實，再送出。"); return;
    }
    setBusy(true); setError("");
    try {
      const result = await post<{id: string; number: string}>("/api/mpc/submit-case", {
        payload, review: confirmedReview, category_id: categoryId, client_request_id: submitRequestId,
      });
      setCaseSent(result);
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  };
  return <div className="page stack">
    <h1>MPC 多人對話人工確認</h1>
    <p className="notice warn">這裡先產生人工核對草稿；第⑥步經再次確認後會正式建立督導案件。此頁不會自動發送緊急警報或建立正式照護紀錄。遇到真實危險請立即求援。</p>
    <div className="card stack">
      <strong>① 匯入誌展的五情境 JSON</strong>
      <input type="file" accept=".json,application/json" onChange={async e => {
        const file = e.target.files?.[0]; if (!file) return;
        if (file.size > MAX_FILE) { setError("JSON 超過 500KB，請使用測試資料"); return; }
        const text = await file.text(); setRaw(text); loadData(text);
      }} />
      <details><summary>或直接貼上單筆／五情境 JSON</summary><textarea value={raw} onChange={e => setRaw(e.target.value)} rows={4} placeholder="貼上 JSON（不得包含真實住民個資）" /><button className="btn" onClick={() => loadData(raw)}>解析 JSON</button></details>
      {scenarioKeys.length > 0 && <label>選擇測試情境： <select value={scenario} onChange={e => chooseScenario(e.target.value)}>{scenarioKeys.map(k => <option key={k} value={k}>{k}</option>)}</select></label>}
      {payload && <><p className="small">事件：{payload.client_event_id}</p><button className="btn primary" disabled={busy} onClick={runPreview}>{busy ? "處理中…" : "② 分析並預覽"}</button></>}
    </div>
    {error && <div className="notice danger" role="alert">{error}</div>}
    {preview && <div className="card stack">
      <h2>③ 確認段落與說話者</h2>
      {(preview.requires_safety_review || hasEnvironmentRisk(payload)) && <p className="notice warn">本情境含高風險或不確定內容，應由督導進一步確認。{hasEnvironmentRisk(payload) ? " 現場可能有犬隻或淹水等環境危害，即使模型原始標記 SAFE，也不代表安全；請先保障人身安全。" : ""}</p>}
      {isCritical(payload, preview, draft) && <p className="notice danger">偵測到緊急情境候選：禁止透過一般督導案件送出，這裡不會建立警報。真實緊急事件請立即求援。</p>}
      {preview.selected_segments.map(seg => <label key={seg.idx} className="card">
        <input type="checkbox" checked={selected.includes(seg.idx)} onChange={e => (setDraft(null), setSelected(v => e.target.checked ? [...v, seg.idx] : v.filter(x => x !== seg.idx)))} /> 第 {seg.idx+1} 段：{seg.masked_text}
        <p className="small muted">AI 角色：{seg.predicted_role || "UNKNOWN"}　風險標記：{seg.safety_flag || "UNKNOWN"}</p>
      </label>)}
      <h3>說話者身分（需要時修正）</h3>
      {Object.entries(preview.speaker_role_suggestions).map(([speaker, suggestion]) => <label key={speaker} className="stack">
        <span>{speaker}（建議：{suggestion}）</span>
        <select value={roleFixes[speaker] ?? suggestion} onChange={e => (setDraft(null), setRoleFixes(v => ({ ...v, [speaker]: e.target.value })))}>
          {roles.map(role => <option value={role} key={role}>{role}</option>)}
        </select>
      </label>)}
      <label className="stack"><span>④ 人工確認摘要</span><textarea rows={5} value={summary} onChange={e => { setDraft(null); setSummary(e.target.value); }} /></label>
      <label><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} /> 我已核對內容，了解這只是草稿，不是正式通報或照護紀錄。</label>
      <button className="btn primary" disabled={busy || !ack || !summary.trim() || selected.length < 1} onClick={confirm}>⑤ 產生人工確認草稿（不送出）</button>
    </div>}
    {draft && <div className="card stack">
      <h2>草稿已產生（未儲存）</h2>
      <p>建議服務代碼：{draft.suggested_service_code}</p>
      <p>需要督導審查：{draft.requires_supervisor_review ? "是" : "否"}</p>
      <p>已建案件：{draft.case_created ? "是" : "否"}；已通知：{draft.notification_sent ? "是" : "否"}</p>
      <textarea readOnly value={draft.reviewed_summary} rows={6} />
      {hasTechnicalText(draft.reviewed_summary) && <p className="notice warn">摘要仍有內部 MPC 技術標籤。請返回第④步改寫成事件事實，再重新產生草稿；不能直接建案。</p>}
      <button className="btn" onClick={() => { void navigator.clipboard?.writeText(draft.reviewed_summary); }}>複製草稿文字（需自行確認）</button>
      {isCritical(payload, preview, draft) ? <p className="notice danger">此草稿屬 P0 緊急候選，不允許使用一般案件送出。真實緊急情況請立即求援，並使用獨立緊急通報。</p> : <div className="card stack">
        <h3>⑥ 人工確認後送交居督（會正式建立案件）</h3>
        <p className="small muted">此按鈕會真的建立待確認案件。請勿將五情境假資料送到正式系統；送出後不會自動產生核准的服務紀錄。</p>
        <label className="stack"><span>選擇案件分類（依所屬機構提供）</span><select value={categoryId} disabled={busy || !!caseSent} onChange={e => { setCategoryId(e.target.value); setSubmitAck(false); }}>
          <option value="">請選擇分類</option>{categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select></label>
        {!caseSent && <label><input type="checkbox" checked={submitAck} onChange={e => setSubmitAck(e.target.checked)} /> 我已核對事件事實、角色及分類，確認要正式建立督導案件，並了解草稿不等於核准紀錄。</label>}
        <button className="btn primary" disabled={busy || !submitAck || !categoryId || !!caseSent || draft.reviewed_summary.length > 1000 || hasTechnicalText(draft.reviewed_summary)} onClick={sendCase}>
          {busy ? "處理中…" : caseSent ? "已建立案件" : "確認正式送交居督"}
        </button>
        {caseSent && <p className="notice">案件 {caseSent.number} 已送出。<Link to={`/liff/cases/${caseSent.id}`}>查看案件</Link></p>}
      </div>}
      <p className="small muted">若需另行人工分類，也可使用原有問題分類頁面。GA09／SC09 表單需使用經核准格式，MPC 摘要不能直接當正式服務紀錄。</p>
      <Link to="/liff/report/entry" className="btn">前往問題分類</Link>
    </div>}
    <Link className="btn" to="/liff">回首頁</Link>
  </div>;
}
