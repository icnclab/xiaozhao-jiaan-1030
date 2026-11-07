import { useEffect, useRef, useState } from "react";
import { api, errorMessage, newRequestId, type Transcript } from "../api";
import { useLiff } from "./LiffApp";
import { beep, checkCapability, Recorder, SilenceDetector, WakeListener } from "./recorder";
import { FallbackEntry } from "./FallbackEntry";

type Phase = "idle" | "listening" | "recording" | "uploading" | "transcribing" | "review" | "failed";

/**
 * 語音提問：按鈕錄音，或「免手模式」以喚醒詞（小照你好）啟動錄音、靜音自動停止。
 * 停止後自動上傳；轉錄草稿先顯示給使用者確認（免手模式有 4 秒取消倒數後自動送出）。
 */
export function VoiceQuestion({ onQuestion, busy, error }: { onQuestion: (text: string, transcriptId: string) => void; busy: boolean; error: string | null }) {
  const { config } = useLiff();
  const cap = useRef(checkCapability()).current;
  const [phase, setPhase] = useState<Phase>("idle");
  const [handsFree, setHandsFree] = useState(false);
  const [pressToTalk, setPressToTalk] = useState(true);
  const pressActive = useRef(false);
  const pressCancelled = useRef(false);
  const stopping = useRef(false);
  const [message, setMessage] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [draft, setDraft] = useState("");
  const [countdown, setCountdown] = useState<number | null>(null);
  const recorder = useRef<Recorder | null>(null);
  const silence = useRef<SilenceDetector | null>(null);
  const wake = useRef<WakeListener | null>(null);
  const timer = useRef<number | null>(null);
  const uploadId = useRef(newRequestId());

  const cleanupListeners = () => {
    wake.current?.stop();
    wake.current = null;
    silence.current?.stop();
    silence.current = null;
    if (timer.current) window.clearInterval(timer.current);
  };

  useEffect(() => () => {
    cleanupListeners();
    recorder.current?.cancel();
  }, []);

  const startRecording = async (viaWake: boolean, held = false) => {
    if (recorder.current) return;
    stopping.current = false;
    if (!cap.ok || !cap.mime) return;
    try {
      const activeRecorder = new Recorder(cap.mime);
      recorder.current = activeRecorder;
      const stream = await activeRecorder.start(config.limits.question_max_sec, () => void stopRecording());
      setPhase("recording");
      setMessage(viaWake ? "聽到喚醒詞，請說問題…（說完停頓即自動送出）" : null);
      timer.current = window.setInterval(() => setElapsed(recorder.current?.elapsedMs ?? 0), 250);
      if (held && pressCancelled.current) {
        activeRecorder.cancel();
        if (recorder.current === activeRecorder) recorder.current = null;
        cleanupListeners();
        setPhase("idle");
        return;
      }
      if (held && !pressActive.current) {
        void stopRecording(); // released while requesting microphone permission
        return;
      }
      if (viaWake) {
        silence.current = new SilenceDetector();
        silence.current.start(stream, () => void stopRecording());
      }
    } catch (e) {
      recorder.current?.cancel();
      recorder.current = null;
      pressActive.current = false;
      setPhase("failed");
      setMessage(`無法開始錄音：${errorMessage(e)}`);
    }
  };

  const stopRecording = async () => {
    if (!recorder.current || stopping.current) return;
    stopping.current = true;
    pressActive.current = false;
    if (timer.current) window.clearInterval(timer.current);
    silence.current?.stop();
    const blob = await recorder.current.stop();
    recorder.current = null;
    setElapsed(0);
    if (blob.size < 2000) {
      setPhase("idle");
      setMessage("錄音太短，請再試一次");
      if (handsFree) startWake();
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
    cleanupListeners();
    setElapsed(0);
    setPhase("idle");
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
    void startRecording(false, true);
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
  const pendingBlob = useRef<Blob | null>(null);

  const pollTranscript = async (id: string) => {
    for (let i = 0; i < 120; i += 1) {
      const t = await api<Transcript>(`/api/transcripts/${id}`);
      if (t.status === "draft") {
        setTranscript(t);
        setDraft(t.segments.map((s) => s.text).join(""));
        setPhase("review");
        uploadId.current = newRequestId();
        if (handsFree) setCountdown(4);
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

  // 免手模式倒數：自動送出，使用者可取消
  useEffect(() => {
    if (countdown === null) return;
    if (countdown === 0) {
      setCountdown(null);
      void confirmAndAsk();
      return;
    }
    const t = window.setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countdown]);

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
      if (handsFree) startWake();
    } catch (e) {
      setMessage(errorMessage(e));
    }
  };

  const startWake = () => {
    if (!WakeListener.supported()) {
      setMessage("此瀏覽器不支援喚醒詞辨識，請改用按鈕錄音");
      setHandsFree(false);
      return;
    }
    wake.current = new WakeListener(config.wake_words);
    setPhase("listening");
    setMessage(`聆聽中：請說「${config.wake_words[0]}，…」`);
    wake.current.start(
      () => {
        beep();
        void startRecording(true);
      },
      (msg) => {
        setMessage(msg);
        setHandsFree(false);
        setPhase("idle");
      },
    );
  };

  const toggleHandsFree = () => {
    if (handsFree) {
      setHandsFree(false);
      cleanupListeners();
      setPhase("idle");
      setMessage(null);
      return;
    }
    if (!window.confirm(`免手模式會持續使用麥克風偵測「${config.wake_words[0]}」（只在本頁開啟時）。喚醒詞辨識使用瀏覽器內建語音服務，音訊可能送到瀏覽器廠商的伺服器；正式提問內容則由本系統處理。要開啟嗎？`)) return;
    setHandsFree(true);
    startWake();
  };

  if (!cap.ok) {
    return <FallbackEntry reason={cap.reason ?? "此裝置不支援錄音"} />;
  }

  return (
    <div className="card stack">
      <div className="row">
        <span className="tag">{config.modes.stt === "mock" ? "STT=模擬" : `STT=${config.modes.stt}`}</span>
        <span className="tag">格式 {cap.mime}</span>
      </div>
      {phase === "idle" && (
        <>
          <div className="row">
            <button type="button" className={`btn ${pressToTalk ? "primary" : ""}`} aria-pressed={pressToTalk} onClick={() => setPressToTalk(true)}>按住說話</button>
            <button type="button" className={`btn ${!pressToTalk ? "primary" : ""}`} aria-pressed={!pressToTalk} onClick={() => setPressToTalk(false)}>按一下錄音</button>
          </div>
          {pressToTalk ? (
            <>
              <p className="small muted">按住下方按鈕說話，放開後自動轉文字；不必說喚醒詞。請先允許瀏覽器使用麥克風。</p>
              <button type="button" className="btn primary big block"
                disabled={busy}
                style={{ touchAction: "none", userSelect: "none", minHeight: 64 }}
                onPointerDown={(e) => { if (e.button !== 0) return; e.preventDefault(); beginPress(); }}
                onKeyDown={(e) => { if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); beginPress(); } }}
              >🎙️ 按住說話・放開辨識</button>
            </>
          ) : <button type="button" className="btn primary big block" onClick={() => void startRecording(false)} disabled={busy}>🎙️ 按一下開始錄音</button>}
          <button className="btn block" onClick={toggleHandsFree}>{handsFree ? "關閉免手模式" : `🗣️ 免手模式（說「${config.wake_words[0]}」）`}</button>
        </>
      )}
      {phase === "listening" && (
        <>
          <div className="notice info">👂 {message}</div>
          <button className="btn block" onClick={toggleHandsFree}>關閉免手模式</button>
        </>
      )}
      {phase === "recording" && (
        <>
          <div className="row"><span className="rec-dot" /> 錄音中 {Math.floor(elapsed / 1000)} 秒／上限 {config.limits.question_max_sec} 秒</div>
          {message && <div className="muted small">{message}</div>}
          {pressToTalk && pressActive.current ? (
            <p className="notice info">🎙️ 正在錄音，放開按鈕即辨識</p>
          ) : (
            <button className="btn danger big block" onClick={() => void stopRecording()}>⏹ 停止並送出</button>
          )}
          <button className="btn block" onClick={() => { recorder.current?.cancel(); recorder.current = null; cleanupListeners(); setPhase("idle"); }}>取消</button>
        </>
      )}
      {(phase === "uploading" || phase === "transcribing") && (
        <div className="notice info">{phase === "uploading" ? "⬆️ 上傳中…" : "📝 轉文字中…（原始錄音轉完即刪除）"}</div>
      )}
      {phase === "review" && transcript && (
        <div className="stack">
          <h3>請確認辨識結果</h3>
          {transcript.segments.some((s) => s.uncertain) && <div className="notice warn">部分內容辨識信心較低，請檢查。</div>}
          <textarea value={draft} onChange={(e) => { setDraft(e.target.value); setCountdown(null); }} />
          {countdown !== null && <div className="notice info">{countdown} 秒後自動送出，修改文字即取消倒數</div>}
          <div className="row">
            <button className="btn primary" disabled={busy || !draft.trim()} onClick={() => { setCountdown(null); void confirmAndAsk(); }}>✅ 用這段提問</button>
            <button className="btn" onClick={() => { setCountdown(null); setTranscript(null); setPhase("idle"); if (handsFree) startWake(); }}>重錄</button>
          </div>
        </div>
      )}
      {phase === "failed" && (
        <div className="stack">
          <div className="notice danger">{message}</div>
          <div className="row">
            {pendingBlob.current && <button className="btn primary" onClick={() => pendingBlob.current && upload(pendingBlob.current)}>重新上傳</button>}
            <button className="btn" onClick={() => { setPhase("idle"); setMessage(null); pendingBlob.current = null; }}>重新錄製</button>
          </div>
        </div>
      )}
      {error && <div className="notice danger">{error}</div>}
      {phase === "idle" && message && <div className="muted small">{message}</div>}
      <FallbackEntry compact />
    </div>
  );
}
