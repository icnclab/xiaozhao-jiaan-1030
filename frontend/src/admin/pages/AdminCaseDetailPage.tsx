import { publicLabel } from '../../publicText';
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, formatTime, newRequestId, post, ROLE_LABELS, type CaseDetail } from "../../api";
import { CitationCard, ErrorBox } from "../../liff/components";
import { useAdmin } from "../AdminApp";

interface UserRow { id: string; display_name: string; role: string; is_active: boolean }

const NOTIFY_LABEL: Record<string, string> = { queued: "通知待送", sending: "送出中", accepted: "LINE 已受理（不代表送達）", failed: "通知失敗", skipped: "略過（無 LINE 或已封鎖）" };

export function AdminCaseDetailPage() {
  const { id } = useParams();
  const { user } = useAdmin();
  const [c, setC] = useState<CaseDetail | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [reply, setReply] = useState("");
  const [closeReason, setCloseReason] = useState("");
  const [assignee, setAssignee] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const replyId = useRef(newRequestId());

  const load = () => api<CaseDetail>(`/api/admin/cases/${id}`).then(setC).catch(setError);
  useEffect(() => {
    void load();
    api<UserRow[]>("/api/admin/users").then((rows) => setUsers(rows.filter((u) => u.role !== "caregiver" && u.is_active))).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  if (!c) return <div><ErrorBox error={error} />{!error && <p className="muted">載入中…</p>}</div>;
  const open = c.status !== "closed";
  // 主任目前僅有案件監督（唯讀）權限，接手／指派／回覆／結案／通知重送屬督導或管理員操作，
  // 後端已限制；前端不提供入口，避免點擊後才被 403 擋下。
  const canProcess = user.role !== "director";
  return (
    <div className="stack">
      <Link to="/admin/cases">← 案件列表</Link>
      <h1>{c.number} <span className={`tag ${c.status === "replied" ? "ok" : "warn"}`}>{c.status_label}</span></h1>
      <div className="row small muted">
        <span>{c.source_label}</span>｜<span>{c.category?.name ?? "未分類"}</span>｜<span>提交：{c.creator?.display_name}</span>｜<span>建立 {formatTime(c.created_at)}</span>｜<span>督導：{c.assignee?.display_name ?? "未指派"}</span>
      </div>
      <div className="card">
        <h3>問題／摘要（已去識別化）</h3>
        <p style={{ whiteSpace: "pre-wrap" }}>{c.summary_masked}</p>
        <p className="small muted">轉交原因：{publicLabel(c.reason)}</p>
      </div>
      {c.qa && (
        <div className="card stack">
          <h3>AI 處理結果 <span className="tag ai">AI 初步參考</span> <span className="tag">{c.qa.outcome}</span></h3>
          <p>{c.qa.answer_text}</p>
          {c.qa.citations.map((x, i) => <CitationCard key={x.id} c={x} index={i + 1} />)}
          {c.retrieval_refs && c.retrieval_refs.length > 0 && (
            <div>
              <p className="small muted">檢索到但未採用的候選條文（供參考，非回答）：</p>
              {c.retrieval_refs.map((r) => (
                <div key={r.chunk_id} className="small">
                  {r.document_title}｜{r.locator}｜{r.version_label}
                  {r.injection_flag && <span className="tag danger">含可疑指令，已排除</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {c.transcript && c.transcript.segments.length > 0 && (
        <div className="card">
          <h3>談話紀錄（已去識別化，照服員確認版）</h3>
          {c.transcript.summary_masked && <p>摘要：{c.transcript.summary_masked}</p>}
          {c.transcript.segments.map((s) => (
            <div key={s.idx} className="small">
              [{s.speaker === "unknown" ? "未辨識" : `${s.speaker.replace("speaker_", "說話者 ")}${c.transcript?.roles[s.speaker] ? `／${ROLE_LABELS[c.transcript.roles[s.speaker]]}` : ""}`}] {s.text}{s.selected && <span className="tag ok">選取</span>}
            </div>
          ))}
        </div>
      )}
      <div className="card stack">
        <h3>回覆與紀錄</h3>
        {c.messages.map((m) => (
          <div key={m.id} className={m.author_role === "caregiver" ? "notice info" : "notice ok"}>
            <div className="small muted">{m.author_role === "caregiver" ? "照服員" : "督導"} {m.author_name}｜{formatTime(m.created_at)}</div>
            <div style={{ whiteSpace: "pre-wrap" }}>{m.body}</div>
          </div>
        ))}
        {c.notifications && c.notifications.length > 0 && (
          <table>
            <thead><tr><th>通知</th><th>狀態</th><th>嘗試</th><th>錯誤碼</th><th>受理時間</th><th></th></tr></thead>
            <tbody>
              {c.notifications.map((n) => (
                <tr key={n.id}>
                  <td>{formatTime(n.created_at)}</td>
                  <td><span className={`tag ${n.status === "accepted" ? "ok" : n.status === "failed" ? "danger" : "warn"}`}>{NOTIFY_LABEL[n.status] ?? n.status}</span></td>
                  <td>{n.attempts}</td>
                  <td>{n.last_error_code ?? "—"}</td>
                  <td>{formatTime(n.accepted_at)}</td>
                  <td>{canProcess && (n.status === "failed" || n.status === "skipped") && <button className="btn" disabled={busy} onClick={() => act(() => post(`/api/admin/notifications/${n.id}/retry`, {}))}>重送</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <ErrorBox error={error} />
        {result && <div className="notice ok">{result}</div>}
        {open && !canProcess && (
          <p className="notice info">主任目前僅能監督／查看此案件；接手、指派、回覆與結案屬居督或管理員操作權限。</p>
        )}
        {open && canProcess && (
          <>
            <div className="row">
              {c.assignee?.id !== user.id && <button className="btn" disabled={busy} onClick={() => act(() => post(`/api/admin/cases/${c.id}/take`, {}))}>我來處理</button>}
              <select value={assignee} onChange={(e) => setAssignee(e.target.value)} style={{ width: "auto" }}>
                <option value="">改派給…</option>
                {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
              </select>
              <button className="btn" disabled={busy || !assignee} onClick={() => act(() => post(`/api/admin/cases/${c.id}/assign`, { assignee_id: assignee }))}>指派</button>
            </div>
            <textarea placeholder="回覆照服員（回覆會保存在系統；LINE 只推播案號與連結）" value={reply} onChange={(e) => setReply(e.target.value)} />
            <div className="row">
              <button
                className="btn primary"
                disabled={busy || !reply.trim()}
                onClick={() => act(async () => {
                  const r = await post<{ reply_saved: boolean; notification: { status: string; last_error_code: string | null } }>(`/api/admin/cases/${c.id}/reply`, { text: reply, client_request_id: replyId.current });
                  replyId.current = newRequestId();
                  setReply("");
                  setResult(`回覆已保存；通知狀態：${NOTIFY_LABEL[r.notification.status] ?? r.notification.status}${r.notification.last_error_code ? `（${r.notification.last_error_code}）` : ""}`);
                })}
              >
                送出回覆
              </button>
              <input type="text" placeholder="結案理由" value={closeReason} onChange={(e) => setCloseReason(e.target.value)} style={{ width: 220 }} />
              <button className="btn danger" disabled={busy || !closeReason.trim()} onClick={() => act(() => post(`/api/admin/cases/${c.id}/close`, { reason: closeReason }))}>結案</button>
            </div>
          </>
        )}
      </div>
      {c.events && (
        <details className="card">
          <summary>狀態歷程（{c.events.length}）</summary>
          <table>
            <tbody>
              {c.events.map((e, i) => (
                <tr key={i}><td>{formatTime(e.created_at)}</td><td>{e.actor}</td><td>{e.kind}</td><td>{e.from_status ?? ""} → {e.to_status ?? ""}</td><td className="small muted">{JSON.stringify(e.data)}</td></tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}
