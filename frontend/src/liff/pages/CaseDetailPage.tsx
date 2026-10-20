import { publicLabel } from '../../publicText';
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, formatTime, newRequestId, post, type CaseDetail } from "../../api";
import { ErrorBox } from "../components";

export function CaseDetailPage() {
  const { id } = useParams();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const requestId = useRef(newRequestId());
  useEffect(() => {
    if (id) api<CaseDetail>(`/api/cases/${id}`).then(setDetail).catch(setError);
  }, [id]);
  if (!detail) return <div className="page"><ErrorBox error={error} />{!error && <p className="muted">載入中…</p>}</div>;
  return (
    <div className="page stack">
      <h1>{detail.number}</h1>
      <div className="row">
        <span className={`tag ${detail.status === "replied" ? "ok" : "warn"}`}>{detail.status_label}</span>
        <span className="tag">{detail.source_label}</span>
        {detail.category && <span className="tag">{detail.category.name}</span>}
      </div>
      <div className="card">
        <p className="muted small">建立 {formatTime(detail.created_at)}｜負責督導：{detail.assignee?.display_name ?? "待指派"}</p>
        <p style={{ whiteSpace: "pre-wrap" }}>{detail.summary_masked}</p>
        <p className="small muted">轉交原因：{publicLabel(detail.reason)}</p>
        {detail.qa_item_id && <Link to={`/liff/answers/${detail.qa_item_id}`}>查看相關 AI 回答</Link>}
      </div>
      <h2>回覆與說明</h2>
      {!detail.first_replied_at && !detail.messages.some((m) => m.author_role === "supervisor" || m.author_role === "admin") && <p className="muted">督導尚未回覆，請等待處理。</p>}
      {detail.messages.map((m) => (
        <div key={m.id} className={`card ${m.author_role === "caregiver" ? "" : "notice ok"}`}>
          <p className="small muted">{m.author_role === "caregiver" ? "我" : `督導 ${m.author_name}`}｜{formatTime(m.created_at)}</p>
          <p style={{ whiteSpace: "pre-wrap" }}>{m.body}</p>
        </div>
      ))}
      {detail.status !== "closed" && (
        <div className="card stack">
          <textarea placeholder="補充說明（請用代稱，不要寫姓名或房號）" value={body} onChange={(e) => setBody(e.target.value)} />
          <ErrorBox error={error} />
          <button
            className="btn primary"
            disabled={busy || !body.trim()}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                setDetail(await post<CaseDetail>(`/api/cases/${detail.id}/messages`, { body, client_request_id: requestId.current }));
                setBody("");
                requestId.current = newRequestId();
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            送出補充
          </button>
        </div>
      )}
    </div>
  );
}
