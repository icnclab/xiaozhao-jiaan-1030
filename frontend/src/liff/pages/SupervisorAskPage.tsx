import { useRef, useState } from "react";
import { errorMessage, newRequestId, post, type Answer } from "../../api";
import { useLiff } from "../LiffApp";
import { AnswerCard, ErrorBox } from "../components";
import { VoiceQuestion } from "../VoiceQuestion";

/** 三角色共用AI助手。督導／主任走專屬RBAC入口；管理員沿用ANY_ROLE的/qa/ask，
 * 不因共用畫面取得額外個案權限。兩者都重用既有STT/RAG/引用流程。 */
export function SupervisorAskPage() {
  const { user } = useLiff();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<"searching" | "organizing" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [mode, setMode] = useState<"text" | "voice">("voice");
  const requestId = useRef(newRequestId());

  if (!(["supervisor", "director", "admin"] as string[]).includes(user.role)) {
    return <div className="page notice warn">此功能僅提供督導、主任或管理員使用，請改用「問 AI」。</div>;
  }

  const assistantTitle = user.role === "admin" ? "管理員 AI 助手" : user.role === "director" ? "主任 AI 助手" : "督導 AI 助手";
  const endpoint = user.role === "admin" ? "/api/qa/ask" : "/api/qa/supervisor-ask";

  const submit = async (text: string, source: "text" | "voice" | "transcript" = "text", transcriptId?: string) => {
    if (busy) return;
    setBusy(true);
    setProgress("searching");
    setError(null);
    const progressTimer = window.setTimeout(() => setProgress("organizing"), 900);
    try {
      const result = await post<Answer>(endpoint, {
        question: text, source, transcript_id: transcriptId ?? null, client_request_id: requestId.current,
      });
      requestId.current = newRequestId();
      setAnswer(result);
    } catch (e) {
      setError(e);
    } finally {
      window.clearTimeout(progressTimer);
      setProgress(null);
      setBusy(false);
    }
  };

  return (
    <div className="page stack">
      <h1>{assistantTitle}</h1>
      <p className="small muted">今天有什麼需要確認的照護規範？</p>
      <a className="btn" href="/admin/cases">← 返回{user.role === "admin" ? "系統管理" : user.role === "director" ? "主任" : "督導"}工作台</a>
      <div className="row">
        <button className={`btn big ${mode === "voice" ? "primary" : ""}`} aria-pressed={mode === "voice"} onClick={() => setMode("voice")}>🎙️ 語音提問</button>
        <button className={`btn ${mode === "text" ? "primary" : ""}`} aria-pressed={mode === "text"} onClick={() => setMode("text")}>⌨️ 文字輸入</button>
      </div>
      {mode === "text" ? (
        <div className="card stack">
          <label htmlFor="supervisor-question">輸入想查詢的規範或案件處置問題</label>
          <textarea
            id="supervisor-question"
            placeholder="例如：居家服務員可以協助代購處方藥嗎？"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <ErrorBox error={error} />
          <button className="btn primary big block" disabled={busy || !question.trim()} onClick={() => submit(question)}>
            {busy ? "查詢中…" : "送出問題"}
          </button>
          <p className="small muted">僅回答規範查詢並附出處；需要人工判斷的個案處置仍由您親自確認，AI回答不代表自動核准。</p>
        </div>
      ) : (
        <VoiceQuestion onQuestion={(text) => submit(text, "voice")} busy={busy} error={error ? errorMessage(error) : null} />
      )}
      {busy && <div className="notice info" role="status" aria-live="polite">
        {progress === "organizing" ? "正在整理回答" : "正在查詢相關文件"}，請勿重複送出。
      </div>}
      {answer && <AnswerCard answer={answer} onChange={setAnswer} />}
    </div>
  );
}
