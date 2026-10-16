import { useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { errorMessage, newRequestId, post, type Answer } from "../../api";
import { useLiff } from "../LiffApp";
import { AnswerCard, ErrorBox } from "../components";
import { VoiceQuestion } from "../VoiceQuestion";

export function AskPage() {
  const { config } = useLiff();
  // 從談話紀錄確認頁帶過來：已確認的逐字稿 ID 與選取的片段文字
  const preset = (useLocation().state as { transcript_id?: string; question?: string } | null) ?? null;
  const [question, setQuestion] = useState(preset?.question ?? "");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [mode, setMode] = useState<"text" | "voice">("text");
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
      <div className="row">
        <button className={`btn ${mode === "text" ? "primary" : ""}`} onClick={() => setMode("text")}>⌨️ 文字</button>
        <button className={`btn ${mode === "voice" ? "primary" : ""}`} onClick={() => setMode("voice")}>🎙️ 語音提問</button>
      </div>
      {mode === "text" ? (
        <div className="card stack">
          <textarea
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
