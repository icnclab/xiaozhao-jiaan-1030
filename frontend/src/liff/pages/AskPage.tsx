import { useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { errorMessage, newRequestId, post, type Answer } from "../../api";
import { useLiff } from "../LiffApp";
import { AnswerCard, ErrorBox } from "../components";
import { VoiceQuestion } from "../VoiceQuestion";

export function AskPage() {
  const { config, user } = useLiff();
  // 從談話紀錄確認頁帶過來：已確認的逐字稿 ID 與選取的片段文字
  const preset = (useLocation().state as { transcript_id?: string; question?: string } | null) ?? null;
  const [question, setQuestion] = useState(preset?.question ?? "");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [mode, setMode] = useState<"text" | "voice">(preset?.question ? "text" : "voice");
  const requestId = useRef(newRequestId());
  const navigate = useNavigate();

  const submit = async (text: string, source: "text" | "voice" | "transcript" = "text", transcriptId?: string) => {
    setBusy(true);
    setError(null);
    try {
      const result = await post<Answer>("/api/qa/ask", {
        question: text,
        source,
        transcript_id: transcriptId ?? null,
        client_request_id: requestId.current,
      });
      requestId.current = newRequestId();
      setAnswer(result);
      navigate(`/liff/answers/${result.id}`, { state: { answer: result, autoPlay: source === "voice" } });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page stack">
      <h1>問 AI</h1>
      <p className="small">登入身分：{{ caregiver: "照服員", supervisor: "居督", director: "主任", admin: "系統管理員" }[user.role] ?? "照服員"}</p>
      <div className="row">
        <button className={`btn big ${mode === "voice" ? "primary" : ""}`} aria-pressed={mode === "voice"} onClick={() => setMode("voice")}>🎙️ 語音提問</button>
        <button className={`btn ${mode === "text" ? "primary" : ""}`} aria-pressed={mode === "text"} onClick={() => setMode("text")}>⌨️ 文字</button>
      </div>
      {mode === "voice" && <p>按語音按鈕開始提問；無法使用麥克風時，可切換「文字」。</p>}
      {mode === "text" ? (
        <div className="card stack">
          <label htmlFor="caregiver-question">輸入想問的問題</label>
          <p id="caregiver-question-help">先輸入問題，再按「送出問題」。請勿填寫姓名或房號。</p>
          <textarea
            id="caregiver-question"
            aria-describedby="caregiver-question-help"
            placeholder={`例如：${config.wake_words[0]}，家屬要我幫住民代購成藥，機構規定可以嗎？`}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <ErrorBox error={error} />
          {preset?.transcript_id && <div className="notice info small">問題來自已確認的談話紀錄；送出時會關聯該紀錄。</div>}
          <button className="btn primary big block" disabled={busy || !question.trim()} onClick={() => submit(question, preset?.transcript_id ? "transcript" : "text", preset?.transcript_id)}>
            {busy ? "查詢中…" : "送出問題"}
          </button>
          <p className="small muted">只回答規範查詢並附出處；醫療、用藥、補助金額問題會轉督導。</p>
        </div>
      ) : (
        <VoiceQuestion onQuestion={(text, transcriptId) => submit(text, "voice", transcriptId)} busy={busy} error={error ? errorMessage(error) : null} />
      )}
      {answer && <AnswerCard answer={answer} onChange={setAnswer} />}
    </div>
  );
}
