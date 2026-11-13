import { useEffect, useRef, useState } from "react";
import { api, errorMessage, newRequestId, type Transcript } from "../api";
import { useLiff } from "./LiffApp";
import { checkCapability, Recorder } from "./recorder";
import { FallbackEntry } from "./FallbackEntry";

type Phase = "idle" | "recording" | "uploading" | "transcribing" | "review" | "failed";
type RecordMode = "click" | "hold";

/**
 * 語音提問：兩個獨立入口共用同一套錄音／STT／確認流程。
 * 「按一下開始錄音」：點一下開始，再點一下停止送出。
 * 「按住說話，放開辨識」：按住期間錄音，放開即停止送出。
 */
export function VoiceQuestion({ onQuestion, busy, error }: { onQuestion: (text: string, transcriptId: string) => void; busy: boolean; error: string | null }) {
  const { config } = useLiff();
  const cap = useRef(checkCapability()).current;
  const [phase, setPhase] = useState<Phase>("idle");
  const [mode, setMode] = useState<RecordMode | null>(null);
  const pressActive = useRef(false);
  const pressCancelled = useRef(false);
  const stopping = useRef(false);
  const [message, setMessage] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [draft, setDraft] = useState("");
  const recorder = useRef<Recorder | null>(null);
  const timer = useRef<number | null>(null);
  const uploadId = useRef(newRequestId());
  const pendingBlob = useRef<Blob | null>(null);

  const cleanupTimer = () => {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
  };

  useEffect(() => () => {
    cleanupTimer();
    recorder.current?.cancel();
  }, []);

  const startRecording = async (recordMode: RecordMode, held = false) => {
    if (recorder.current) return;
    stopping.current = false;
    if (!cap.ok || !cap.mime) return;
    try {
      const activeRecorder = new Recorder(cap.mime);
      recorder.current = activeRecorder;
      await activeRecorder.start(config.limits.question_max_sec, () => void stopRecording());
      setMode(recordMode);
      setPhase("recording");
      setMessage(null);
      timer.current = window.setInterval(() => setElapsed(recorder.current?.elapsedMs ?? 0), 250);
      if (held && pressCancelled.current) {
        activeRecorder.cancel();
        if (recorder.current === activeRecorder) recorder.current = null;
        cleanupTimer();
        setPhase("idle");
        setMode(null);
        return;
      }
      if (held && !pressActive.current) {
        void stopRecording(); // released while requesting microphone permission
        return;
      }
    } catch (e) {
      recorder.current?.cancel();
      recorder.current = null;
      pressActive.current = false;
      setPhase("failed");
      setMode(null);
      setMessage(`無法開始錄音：${errorMessage(e)}`);
    }
  };

  const stopRecording = async () => {
    if (!recorder.current || stopping.current) return;
    stopping.current = true;
    pressActive.current = false;
    cleanupTimer();
    const blob = await recorder.current.stop();
    recorder.current = null;
    setElapsed(0);
    if (blob.size < 2000) {
      setPhase("idle");
      setMode(null);
      setMessage("錄音太短，請再試一次");
      return;
    }
    await upload(blob);
  };

  // Keep release handlers on window because the idle button is replaced while recording.
  const endPress = () => {
    if (!pressActive.current) return;
    pressActive.current = false;
    window.removeEventListener("pointerup", endPress);
    window.removeEventListener("pointercancel", cancelPress);
    window.removeEventListener("keyup", releaseKey);
    if (recorder.current?.elapsedMs) void stopRecording();
    // If mic permission is pending, startRecording() will stop when permission resolves.
  };
  const cancelPress = () => {
    pressCancelled.current = true;
    pressActive.current = false;
    window.removeEventListener("pointerup", endPress);
    window.removeEventListener("pointercancel", cancelPress);
    window.removeEventListener("keyup", releaseKey);
    recorder.current?.cancel();
    recorder.current = null;
    cleanupTimer();
    setElapsed(0);
    setPhase("idle");
    setMode(null);
    setMessage("錄音已取消");
  };
  const releaseKey = (e: KeyboardEvent) => {
    if (e.key === " " || e.key === "Enter") endPress();
  };
  const beginPress = () => {
    if (phase !== "idle" || busy || pressActive.current) return;
    pressCancelled.current = false;
    pressActive.current = true;
    window.addEventListener("pointerup", endPress);
    window.addEventListener("pointercancel", cancelPress);
    window.addEventListener("keyup", releaseKey);
    void startRecording("hold", true);
  };

  const toggleClickRecording = () => {
    if (phase === "idle") {
      if (busy) return;
      void startRecording("click");
    } else if (phase === "recording" && mode === "click") {
      void stopRecording();
    }
  };

  const upload = async (blob: Blob) => {
    setPhase("uploading");
    const form = new FormData();
    form.append("file", blob, "question.webm");
    form.append("mode", "question");
    form.append("client_upload_id", uploadId.current);
    form.append("consent_confirmed", "false");
    try {
      const result = await api<{ transcript_id: string; status: string }>("/api/audio/uploads", { method: "POST", body: form });
      setPhase("transcribing");
      await pollTranscript(result.transcript_id);
    } catch (e) {
      setPhase("failed");
      setMessage(`上傳失敗：${errorMessage(e)}（可按「重新上傳」）`);
      pendingBlob.current = blob;
    }
  };

  const pollTranscript = async (id: string) => {
    for (let i = 0; i < 120; i += 1) {
      const t = await api<Transcript>(`/api/transcripts/${id}`);
      if (t.status === "draft") {
        setTranscript(t);
        setDraft(t.segments.map((s) => s.text).join(""));
        setPhase("review");
        uploadId.current = newRequestId();
        return;
      }
      if (["failed", "expired", "rejected", "cancelled"].includes(t.status)) {
        setPhase("failed");
        setMessage(t.error_message ?? "轉文字失敗");
        uploadId.current = newRequestId();
        return;
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
    setPhase("failed");
    setMessage("轉文字逾時，請稍後在「錄音」頁查看或重新錄製");
  };

  const confirmAndAsk = async () => {
    if (!transcript) return;
    try {
      await api(`/api/transcripts/${transcript.id}/confirm`, {
        method: "POST",
        body: JSON.stringify({ segments: draft !== transcript.segments.map((s) => s.text).join("") ? [{ idx: transcript.segments[0].idx, text: draft }, ...transcript.segments.slice(1).map((s) => ({ idx: s.idx, text: "" }))] : [], roles: {}, selected_idx: transcript.segments.map((s) => s.idx), summary: null }),
      });
      onQuestion(draft, transcript.id);
      setTranscript(null);
      setPhase("idle");
      setMode(null);
    } catch (e) {
      setMessage(errorMessage(e));
    }
  };

  if (!cap.ok) {
    return <FallbackEntry reason={cap.reason ?? "此裝置不支援錄音"} />;
  }

  return (
    <div className="card stack">
      {phase === "idle" && (
        <>
          <p className="small muted">按一下開始錄音，說完再按一下即可辨識；或改用下方按住說話，放開即辨識。請先允許瀏覽器使用麥克風。</p>
          <button type="button" className="btn primary big block" onClick={toggleClickRecording} disabled={busy}>
            🎙️ 按一下開始錄音
          </button>
          <button type="button" className="btn block"
            disabled={busy}
            style={{ touchAction: "none", userSelect: "none", minHeight: 64 }}
            onPointerDown={(e) => { if (e.button !== 0) return; e.preventDefault(); beginPress(); }}
            onKeyDown={(e) => { if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); beginPress(); } }}
          >按住說話，放開辨識</button>
        </>
      )}
      {phase === "recording" && mode === "click" && (
        <>
          <div className="row"><span className="rec-dot" /> 錄音中 {Math.floor(elapsed / 1000)} 秒／上限 {config.limits.question_max_sec} 秒</div>
          <button className="btn danger big block" onClick={toggleClickRecording}>停止錄音並辨識</button>
          <button className="btn block" onClick={() => { recorder.current?.cancel(); recorder.current = null; cleanupTimer(); setPhase("idle"); setMode(null); }}>取消</button>
        </>
      )}
      {phase === "recording" && mode === "hold" && (
        <>
          <div className="row"><span className="rec-dot" /> 錄音中 {Math.floor(elapsed / 1000)} 秒／上限 {config.limits.question_max_sec} 秒</div>
          <p className="notice info">🎙️ 正在錄音，放開按鈕即辨識</p>
        </>
      )}
      {(phase === "uploading" || phase === "transcribing") && (
        <div className="notice info">{phase === "uploading" ? "⬆️ 上傳中…" : "📝 轉文字中…（原始錄音轉完即刪除）"}</div>
      )}
      {phase === "review" && transcript && (
        <div className="stack">
          <h3>請確認辨識結果</h3>
          {transcript.segments.some((s) => s.uncertain) && <div className="notice warn">部分內容辨識信心較低，請檢查。</div>}
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} />
          <div className="row">
            <button className="btn primary" disabled={busy || !draft.trim()} onClick={() => void confirmAndAsk()}>✅ 用這段提問</button>
            <button className="btn" onClick={() => { setTranscript(null); setPhase("idle"); setMode(null); }}>重錄</button>
          </div>
        </div>
      )}
      {phase === "failed" && (
        <div className="stack">
          <div className="notice danger">{message}</div>
          <div className="row">
            {pendingBlob.current && <button className="btn primary" onClick={() => pendingBlob.current && upload(pendingBlob.current)}>重新上傳</button>}
            <button className="btn" onClick={() => { setPhase("idle"); setMode(null); setMessage(null); pendingBlob.current = null; }}>重新錄製</button>
          </div>
        </div>
      )}
      {error && <div className="notice danger">{error}</div>}
      {phase === "idle" && message && <div className="muted small">{message}</div>}
      <FallbackEntry compact />
    </div>
  );
}
