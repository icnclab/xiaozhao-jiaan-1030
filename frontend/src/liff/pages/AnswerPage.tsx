import { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { api, type Answer } from "../../api";
import { useLiff } from "../LiffApp";
import { AnswerCard, ErrorBox } from "../components";

export function AnswerPage() {
  const { user } = useLiff();
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
      <h1>提問紀錄</h1>
      <p className="notice info">每次提問是一筆紀錄；需居督處理時，另有待確認案件編號。</p>
      {answer && <p style={{overflowWrap:"anywhere"}}>提問紀錄編號：{answer.id}</p>}
      <ErrorBox error={error} />
      {answer ? <AnswerCard answer={answer} onChange={setAnswer} autoPlay={Boolean(initial?.autoPlay)} conversationId={user.role === "caregiver" ? answer.conversation_id : null} /> : !error && <p className="muted">載入中…</p>}
    </div>
  );
}
