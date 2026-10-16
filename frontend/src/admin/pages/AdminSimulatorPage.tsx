import { useEffect, useState } from "react";
import { api, formatTime } from "../../api";
import { ErrorBox } from "../../liff/components";

interface DevUser { username: string; display_name: string; line_user_id: string | null; blocked: boolean }
interface Outbox { id: number; kind: string; to: string | null; messages: { type: string; text?: string; originalContentUrl?: string; quickReply?: { items: { action: { label: string; data?: string; uri?: string } }[] } }[]; created_at: string }

/**
 * LINE 模擬器（只在 LINE_MODE=mock 且非正式環境出現）：
 * 以照服員身分送出文字／語音／postback／follow／unfollow 事件；事件仍經真實的簽章驗證與去重。
 * 右側顯示 bot「將會」回覆／推播的內容。這是模擬，不代表真實 LINE 串接。
 */
export function AdminSimulatorPage() {
  const [users, setUsers] = useState<DevUser[]>([]);
  const [username, setUsername] = useState("");
  const [text, setText] = useState("小照你好，家屬要我幫住民代購成藥可以嗎？");
  const [file, setFile] = useState<File | null>(null);
  const [outbox, setOutbox] = useState<Outbox[]>([]);
  const [last, setLast] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  const [health, setHealth] = useState<{ worker_heartbeat_age_sec: number | null } | null>(null);

  const refresh = () => {
    api<Outbox[]>("/api/dev/line/outbox").then(setOutbox).catch(setError);
    api<typeof health>("/api/healthz").then(setHealth).catch(() => undefined);
  };
  useEffect(() => {
    api<DevUser[]>("/api/dev/line/users").then((u) => { setUsers(u); if (u[0]) setUsername(u[0].username); }).catch(setError);
    refresh();
    const t = window.setInterval(refresh, 3000);
    return () => window.clearInterval(t);
  }, []);

  const send = async (kind: string, extra: Record<string, string> = {}) => {
    setError(null);
    const form = new FormData();
    form.append("kind", kind);
    form.append("username", username);
    Object.entries(extra).forEach(([k, v]) => form.append(k, v));
    if (kind === "audio" && file) form.append("audio", file);
    try {
      setLast(await api("/api/dev/line/simulate", { method: "POST", body: form }));
      window.setTimeout(refresh, 1500);
    } catch (e) {
      setError(e);
    }
  };

  const lastBody = (last as { body?: unknown } | null)?.body;
  return (
    <div className="stack">
      <h1>LINE 模擬器 <span className="tag mock">模擬，不代表真實串接</span></h1>
      <p className="muted small">事件由本機組出、以測試 channel secret 簽章後打 /api/line/webhook，走與真實 LINE 相同的驗簽、去重、背景處理；reply／push 寫入模擬信箱。
        Worker 心跳：{health?.worker_heartbeat_age_sec === null || health?.worker_heartbeat_age_sec === undefined ? <span className="tag danger">未偵測到 worker（請啟動 python -m app.worker）</span> : `${health.worker_heartbeat_age_sec}s 前`}</p>
      <ErrorBox error={error} />
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="card stack" style={{ flex: 1, minWidth: 320 }}>
          <label className="small">以誰的身分</label>
          <select value={username} onChange={(e) => setUsername(e.target.value)}>
            {users.map((u) => <option key={u.username} value={u.username}>{u.display_name}（{u.username}）{u.line_user_id ? "" : "－未綁定"}{u.blocked ? "－已封鎖" : ""}</option>)}
          </select>
          <textarea value={text} onChange={(e) => setText(e.target.value)} />
          <div className="row">
            <button className="btn primary" onClick={() => send("text", { text })}>傳文字訊息</button>
            <button className="btn" onClick={() => send("follow")}>加好友（follow）</button>
            <button className="btn" onClick={() => send("unfollow")}>封鎖（unfollow）</button>
          </div>
          <div className="row">
            <input type="file" accept="audio/*,.wav,.m4a,.webm,.mp3" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <button className="btn" disabled={!file} onClick={() => send("audio")}>傳語音訊息</button>
          </div>
          <div className="row">
            <button className="btn" onClick={() => lastBody && send("text", { redeliver_of: JSON.stringify(lastBody) })} disabled={!lastBody}>重送上一則 webhook（isRedelivery）</button>
          </div>
          <p className="small muted">快速回覆按鈕請直接在右側點「模擬點擊」，會以 postback 事件送回。</p>
          {last ? <details className="small"><summary>上一次送出的 webhook body</summary><pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(last, null, 1)}</pre></details> : null}
        </div>
        <div className="card stack" style={{ flex: 1, minWidth: 320 }}>
          <div className="row"><h3>bot 回覆／推播（模擬信箱）</h3><button className="btn" onClick={refresh}>更新</button></div>
          {outbox.map((o) => (
            <div key={o.id} className="notice info">
              <div className="small muted">{formatTime(o.created_at)}｜{o.kind}｜{o.to}</div>
              {o.messages.map((m, i) => (
                <div key={i}>
                  <div style={{ whiteSpace: "pre-wrap" }}>{m.type === "audio" ? <audio controls src={m.originalContentUrl} /> : m.text}</div>
                  {m.quickReply && (
                    <div className="row">
                      {m.quickReply.items.map((it, j) => it.action.data ? (
                        <button key={j} className="btn" onClick={() => send("postback", { postback: it.action.data! })}>模擬點擊：{it.action.label}</button>
                      ) : (
                        <a key={j} className="btn" href={it.action.uri} target="_blank" rel="noreferrer">{it.action.label} ↗</a>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ))}
          {outbox.length === 0 && <p className="muted">尚無訊息</p>}
        </div>
      </div>
    </div>
  );
}
