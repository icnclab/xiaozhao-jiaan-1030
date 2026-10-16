import { useState } from "react";
import { api, post, type Answer } from "../api";
import { publicMessage } from '../publicText';
import { FeedbackFields, emptyCorrection } from "./FeedbackFields";

export function FeedbackCollector({ answer, onChange }: { answer: Answer; onChange: (a: Answer) => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [value, setValue] = useState(emptyCorrection);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const message = (e: unknown) => publicMessage((e as { message?: string })?.message);
  const begin = async () => {
    setBusy(true); setError(null);
    try {
      const existing = await api<{ id: string; status: string } | null>(`/api/quality/qa/${answer.id}/feedback`);
      if (existing) setSaved(existing.status);
      else setOpen(true);
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  };
  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const result = await post<{ id: string; status: string }>(`/api/quality/qa/${answer.id}/feedback`, value);
      setSaved(result.status); setOpen(false);
      onChange({ ...answer, feedback_wrong: true });
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  };
  return <div className="stack">
    {saved ? <span className="tag warn">已提交品質回饋（{saved === "pending_review" ? "待審核" : saved === "verified" ? "已驗證" : "已駁回"}）</span>
      : open ? <>
        <p>原問答與引用來源會隨回饋保存，交由督導／管理員審核。</p>
        <FeedbackFields value={value} onChange={setValue} disabled={busy} />
        <div className="row"><button className="btn primary" disabled={busy} onClick={submit}>{busy ? "送出中…" : "提交品質回饋"}</button>
          <button className="btn" disabled={busy} onClick={() => setOpen(false)}>取消</button></div>
      </> : <button className="btn" disabled={busy} onClick={begin}>❌ 回答有誤</button>}
    {error && <div role="alert" className="notice danger">{error}</div>}
  </div>;
}
