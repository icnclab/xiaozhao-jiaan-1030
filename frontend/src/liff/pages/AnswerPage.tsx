import { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { api, type Answer } from "../../api";
import { AnswerCard, ErrorBox } from "../components";

export function AnswerPage() {
  const { id } = useParams();
  const location = useLocation();
  const initial = (location.state as { answer?: Answer; autoPlay?: boolean } | null) ?? null;
  // location.state 只當作首次渲染的佔位（避免閃爍）；一律再向後端取最新狀態（TTS、案件、回饋可能已變）
  const [answer, setAnswer] = useState<Answer | null>(initial?.answer ?? null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (id) api<Answer>(`/api/qa/${id}`).then(setAnswer).catch(setError);
  }, [id]);
  return (
    <div className="page stack">
      <h1>回答</h1>
      <ErrorBox error={error} />
      {answer ? <AnswerCard answer={answer} onChange={setAnswer} autoPlay={Boolean(initial?.autoPlay)} /> : !error && <p className="muted">載入中…</p>}
    </div>
  );
}
