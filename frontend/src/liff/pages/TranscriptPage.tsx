import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, errorMessage, formatMs, post, ROLE_LABELS, type Segment, type Transcript } from "../../api";
import { ErrorBox } from "../components";

const SPEAKERS = ["unknown", "speaker_1", "speaker_2", "speaker_3", "speaker_4"];

/**
 * 轉錄確認頁：顯示分段文字、起訖時間、說話者標記；照服員修正文字、指定 speaker 與角色、
 * 勾選要拿去查詢或送交的片段、填摘要，確認後只保存遮罩版。無法分辨的說話者維持「未辨識」。
 */
export function TranscriptPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [t, setT] = useState<Transcript | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [edits, setEdits] = useState<Record<number, Partial<Segment>>>({});
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let timer: number | null = null;
    const load = async () => {
      try {
        const data = await api<Transcript>(`/api/transcripts/${id}`);
        setT(data);
        if (data.status === "confirmed") setRoles(data.roles);
        if (["queued", "transcribing"].includes(data.status)) timer = window.setTimeout(load, 1500);
      } catch (e) {
        setError(e);
      }
    };
    void load();
    return () => {
      if (timer) window.clearTimeout(timer);
    };
  }, [id]);

  const segments = useMemo(() => t?.segments.map((s) => ({ ...s, ...edits[s.idx] })) ?? [], [t, edits]);
  const usedSpeakers = useMemo(() => Array.from(new Set(segments.map((s) => s.speaker).filter((s) => s !== "unknown"))), [segments]);

  const confirm = async () => {
    if (!t) return;
    setBusy(true);
    setError(null);
    try {
      const body = {
        segments: Object.entries(edits).map(([idx, e]) => ({ idx: Number(idx), ...e })),
        roles,
        selected_idx: Array.from(selected),
        summary: summary || null,
      };
      setT(await post<Transcript>(`/api/transcripts/${t.id}/confirm`, body));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const retry = async () => {
    if (!t) return;
    setBusy(true);
    try {
      setT(await post<Transcript>(`/api/transcripts/${t.id}/retry`, {}));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const selectedText = segments.filter((s) => selected.has(s.idx)).map((s) => s.text).join("");

  if (!t) return <div className="page"><ErrorBox error={error} />{!error && <p className="muted">載入中…</p>}</div>;

  return (
    <div className="page stack">
      <h1>{t.mode === "conversation" ? "談話紀錄" : "語音提問"}</h1>
      <div className="row">
        <span className="tag">{t.status}</span>
        <span className="tag">{t.stt_provider === "mock" ? "STT=模擬" : `STT=${t.stt_provider ?? "—"}`}</span>
        {t.audio_duration_ms ? <span className="tag">{formatMs(t.audio_duration_ms)}</span> : null}
        {t.audio_deleted && <span className="tag ok">原始錄音已刪除</span>}
      </div>
      {["queued", "transcribing"].includes(t.status) && <div className="notice info">📝 {t.status === "queued" ? "等待轉文字…" : "轉文字中…"}</div>}
      {["failed", "expired", "rejected"].includes(t.status) && (
        <div className="stack">
          <div className="notice danger">{t.error_message ?? "處理失敗"}</div>
          {t.status === "failed" && !t.audio_deleted ? (
            <button className="btn primary" onClick={retry} disabled={busy}>重試轉文字</button>
          ) : (
            <Link className="btn primary" to="/liff/record">重新錄製</Link>
          )}
        </div>
      )}
      {(t.status === "draft" || t.status === "confirmed") && (
        <>
          {t.status === "draft" && (
            <div className="notice warn small">
              以下是未遮罩的辨識草稿，只有您看得到，逾時未確認會自動清除（{t.draft_expires_at ? new Date(t.draft_expires_at).toLocaleString("zh-TW") : ""}）。
              說話者預設「未辨識」；系統不會憑聲音猜誰是長輩或家屬，請您指定。
            </div>
          )}
          <div className="card">
            {segments.map((s) => (
              <div key={s.idx} className={`seg ${s.uncertain ? "uncertain" : ""}`}>
                <div>
                  <div className="time">{formatMs(s.start_ms)}–{formatMs(s.end_ms)}</div>
                  {t.status === "draft" ? (
                    <select value={s.speaker} onChange={(e) => setEdits({ ...edits, [s.idx]: { ...edits[s.idx], speaker: e.target.value } })}>
                      {SPEAKERS.map((sp) => <option key={sp} value={sp}>{sp === "unknown" ? "未辨識" : sp.replace("speaker_", "說話者 ")}</option>)}
                    </select>
                  ) : (
                    <div className="small">{s.speaker === "unknown" ? "未辨識" : `${s.speaker.replace("speaker_", "說話者 ")}${t.roles[s.speaker] ? `（${ROLE_LABELS[t.roles[s.speaker]]}）` : ""}`}</div>
                  )}
                  {t.status === "draft" && (
                    <label className="small"><input type="checkbox" checked={selected.has(s.idx)} onChange={(e) => { const next = new Set(selected); e.target.checked ? next.add(s.idx) : next.delete(s.idx); setSelected(next); }} /> 選取</label>
                  )}
                </div>
                <div>
                  {t.status === "draft" ? (
                    <textarea value={s.text} onChange={(e) => setEdits({ ...edits, [s.idx]: { ...edits[s.idx], text: e.target.value } })} />
                  ) : (
                    <p style={{ whiteSpace: "pre-wrap" }}>{s.text}{s.edited && <span className="tag">已修正</span>}{s.selected && <span className="tag ok">已選取</span>}</p>
                  )}
                  {s.uncertain && <span className="tag warn">辨識不確定，請確認</span>}
                </div>
              </div>
            ))}
          </div>
          {t.status === "draft" && (
            <div className="card stack">
              <h3>說話者對應的角色</h3>
              {usedSpeakers.length === 0 && <p className="muted small">先在上方為片段指定「說話者 1、2…」，再對應角色；分不出來就維持未辨識。</p>}
              {usedSpeakers.map((sp) => (
                <div key={sp} className="row">
                  <span>{sp.replace("speaker_", "說話者 ")}＝</span>
                  <select value={roles[sp] ?? "unknown"} onChange={(e) => setRoles({ ...roles, [sp]: e.target.value })} style={{ width: "auto" }}>
                    {Object.entries(ROLE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
              ))}
              <h3>摘要（選填，會一併送交督導）</h3>
              <textarea value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="例如：家屬要求每晚多餵一次點心，住民有糖尿病紀錄" />
              <ErrorBox error={error} />
              <button className="btn primary big block" onClick={confirm} disabled={busy}>{busy ? "保存中…" : "✅ 確認送出（保存遮罩版，刪除原始草稿）"}</button>
              <p className="small muted">確認後只保存去識別化版本與修訂軌跡；談話內容不會自動送進問答或知識庫。</p>
            </div>
          )}
          {t.status === "confirmed" && (
            <div className="card stack">
              <h3>接下來</h3>
              {t.summary_masked && <p className="small">摘要：{t.summary_masked}</p>}
              <button
                className="btn primary block"
                onClick={() => navigate("/liff/ask", { state: { transcript_id: t.id, question: t.segments.filter((s) => s.selected).map((s) => s.text).join("") || t.summary_masked || "" } })}
              >
                💬 用選取的片段／摘要向小照提問
              </button>
              <button className="btn block" onClick={() => navigate("/liff/report", { state: { transcript_id: t.id, summary: t.summary_masked ?? "" } })}>📋 分類回報並送交督導</button>
            </div>
          )}
        </>
      )}
      {t.status === "draft" && selectedText && <p className="small muted">已選取：{selectedText.slice(0, 80)}…</p>}
      {t.status !== "draft" && error ? <div className="notice danger">{errorMessage(error)}</div> : null}
    </div>
  );
}
