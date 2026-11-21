import { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { api, type Answer } from "../../api";
import { useLiff } from "../LiffApp";
import { AnswerCard, ErrorBox } from "../components";

/** 依角色決定返回連結，不依賴瀏覽器歷史：直接開啟此頁（深連結）或重新整理後，
 * 只要 session 還在，useLiff() 讀到的角色就一定正確，不會跳回正式第六版（同源相對路徑）。*/
function backNav(role: string): { to: string; label: string } {
  if (role === "director") return { to: "/admin/cases", label: "返回主任工作台" };
  if (role === "supervisor") return { to: "/admin/cases", label: "返回督導工作台" };
  if (role === "admin") return { to: "/admin/cases", label: "返回系統管理" };
  return { to: "/liff/ask", label: "返回 AI 助手" };
}

export function AnswerPage() {
  const { id } = useParams();
  const location = useLocation();
  const { user } = useLiff();
  const initial = (location.state as { answer?: Answer; autoPlay?: boolean } | null) ?? null;
  // location.state 只當作首次渲染的佔位（避免閃爍）；一律再向後端取最新狀態（TTS、案件、回饋可能已變）
  const [answer, setAnswer] = useState<Answer | null>(initial?.answer ?? null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (id) api<Answer>(`/api/qa/${id}`).then(setAnswer).catch(setError);
  }, [id]);
  const back = backNav(user.role);
  return (
    <div className="page stack">
      <h1>提問紀錄</h1>
      <a className="btn" href={back.to}>← {back.label}</a>
      <p className="notice info">每次提問是一筆紀錄；需居督處理時，另有待確認案件編號。</p>
      {answer && <p style={{overflowWrap:"anywhere"}}>提問紀錄編號：{answer.id}</p>}
      <ErrorBox error={error} />
      {answer ? <AnswerCard answer={answer} onChange={setAnswer} autoPlay={Boolean(initial?.autoPlay)} /> : !error && <p className="muted">載入中…</p>}
    </div>
  );
}
