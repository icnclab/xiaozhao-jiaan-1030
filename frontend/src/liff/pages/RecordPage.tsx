import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorMessage, formatMs, newRequestId, type Transcript } from "../../api";
import { useLiff } from "../LiffApp";
import { ErrorBox } from "../components";
import { FallbackEntry } from "../FallbackEntry";
import { checkCapability, Recorder } from "../recorder";

type Phase = "idle" | "recording" | "uploading" | "done" | "failed";

/**
 * 談話紀錄錄音頁：告知同意 → 開始／停止／取消 → 停止後自動上傳 → 轉到確認頁。
 * 談話紀錄不會自動送進問答；由照服員在確認頁選取問題或確認摘要後再查詢或送交。
 */
export function RecordPage() {
  const { config } = useLiff();
  const cap = useRef(checkCapability()).current;
  const [consent, setConsent] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [recent, setRecent] = useState<Transcript[]>([]);
  const recorder = useRef<Recorder | null>(null);
  const timer = useRef<number | null>(null);
  const uploadId = useRef(newRequestId());
  const pending = useRef<Blob | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api<Transcript[]>("/api/transcripts").then(setRecent).catch(() => setRecent([]));
    return () => {
      recorder.current?.cancel();
      if (timer.current) window.clearInterval(timer.current);
    };
  }, []);

  const start = async () => {
    if (!cap.mime) return;
    try {
      recorder.current = new Recorder(cap.mime);
      await recorder.current.start(config.limits.conversation_max_sec, () => void stop());
      setPhase("recording");
      timer.current = window.setInterval(() => setElapsed(recorder.current?.elapsedMs ?? 0), 500);
    } catch (e) {
      setPhase("failed");
      setMessage(`無法開始錄音：${errorMessage(e)}`);
    }
  };

  const stop = async () => {
    if (!recorder.current) return;
    if (timer.current) window.clearInterval(timer.current);
    const blob = await recorder.current.stop();
    recorder.current = null;
    setElapsed(0);
    await upload(blob);
  };

  const upload = async (blob: Blob) => {
    setPhase("uploading");
    setMessage(null);
    const form = new FormData();
    form.append("file", blob, "conversation.webm");
    form.append("mode", "conversation");
    form.append("client_upload_id", uploadId.current);
    form.append("consent_confirmed", "true");
    try {
      const result = await api<{ transcript_id: string }>("/api/audio/uploads", { method: "POST", body: form });
      uploadId.current = newRequestId();
      pending.current = null;
      navigate(`/liff/record/${result.transcript_id}`);
    } catch (e) {
      pending.current = blob;
      setPhase("failed");
      setMessage(`上傳失敗：${errorMessage(e)}`);
    }
  };

  const cancel = () => {
    recorder.current?.cancel();
    recorder.current = null;
    if (timer.current) window.clearInterval(timer.current);
    setElapsed(0);
    setPhase("idle");
  };

  const statusLabel: Record<string, string> = {
    queued: "等待轉文字", transcribing: "轉文字中", draft: "待確認", confirmed: "已確認", failed: "失敗",
    expired: "已過期", cancelled: "已取消", rejected: "已拒絕",
  };

  return (
    <div className="page stack">
      <h1>錄音／談話紀錄</h1>
      {!cap.ok ? (
        <FallbackEntry reason={cap.reason ?? "此裝置不支援錄音"} />
      ) : (
        <div className="card stack">
          <div className="notice info small">{config.consent_text}</div>
          {phase === "idle" && (
            <>
              <p>請先勾選錄音同意事項，才能開始錄音。</p>
              <label className="row">
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} style={{ width: 22, height: 22 }} />
                我已告知在場的人錄音用途並取得同意
              </label>
              <button className="btn primary big block" disabled={!consent} onClick={start}>🎙️ 開始錄音（上限 {Math.round(config.limits.conversation_max_sec / 60)} 分鐘）</button>
              <span className="tag">格式 {cap.mime}</span>
            </>
          )}
          {phase === "recording" && (
            <>
              <div className="row"><span className="rec-dot" /> <strong>錄音中</strong> {formatMs(elapsed)}／{formatMs(config.limits.conversation_max_sec * 1000)}</div>
              <button className="btn danger big block" onClick={() => void stop()}>⏹ 停止並上傳</button>
              <button className="btn block" onClick={cancel}>取消（不保存）</button>
            </>
          )}
          {phase === "uploading" && <div className="notice info">⬆️ 上傳中…上傳完成會自動開始轉文字。</div>}
          {phase === "failed" && (
            <div className="stack">
              <div className="notice danger">{message}</div>
              <div className="row">
                {pending.current && <button className="btn primary" onClick={() => pending.current && upload(pending.current)}>重新上傳（不會重複建立紀錄）</button>}
                <button className="btn" onClick={() => { pending.current = null; setPhase("idle"); }}>重新錄製</button>
              </div>
            </div>
          )}
          <FallbackEntry compact />
        </div>
      )}
      <h2>最近的紀錄</h2>
      <ErrorBox error={null} />
      {recent.length === 0 && <p className="muted">尚無紀錄。</p>}
      {recent.map((t) => (
        <Link key={t.id} to={`/liff/record/${t.id}`} className="card" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="row">
            <span className={`tag ${t.status === "draft" ? "warn" : t.status === "confirmed" ? "ok" : ""}`}>{statusLabel[t.status] ?? t.status}</span>
            <span className="small muted">{t.mode === "conversation" ? "談話紀錄" : "語音提問"}｜{t.audio_duration_ms ? formatMs(t.audio_duration_ms) : "—"}</span>
          </div>
          {t.summary_masked && <p className="small">{t.summary_masked}</p>}
          {t.error_message && <p className="small" style={{ color: "var(--danger)" }}>{t.error_message}</p>}
        </Link>
      ))}
    </div>
  );
}
