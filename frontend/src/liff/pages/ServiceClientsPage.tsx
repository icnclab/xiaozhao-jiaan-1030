import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, post, type Jiaan1030Catalog, type Jiaan1030ServiceClient, type Jiaan1030ServiceDraft } from "../../api";
import { ErrorBox } from "../components";
import { useLiff } from "../LiffApp";

const DRAFT_STATUS_LABEL: Record<string, string> = { draft: "草稿（未送出）", submitted: "已送出" };

/** GA09/SC09 服務個案（測試用假資料）：建立/列出個案、進入服務紀錄表單、授權/撤銷存取。
 * 僅列出目前使用者可存取的個案（自己建立的，或已被明確授權的）。
 * 授權/撤銷僅對自己建立的個案提供入口（後端同時也會擋非建立者/非主任/admin 的授權請求）。
 * 已提供同機構督導/主任清單及有效授權狀態。 */
interface GrantableReviewer { id: string; username: string; display_name: string; role: string }
interface ClientGrant {
  id: string; service_client_id: string; grantee_id: string;
  grantee_name: string; grantee_username: string; grantee_role: string;
  revoked_at: string | null;
}

export function ServiceClientsPage() {
  const { user } = useLiff();
  const [clients, setClients] = useState<Jiaan1030ServiceClient[] | null>(null);
  const [approvedForms, setApprovedForms] = useState<Jiaan1030Catalog["service_forms"]>([]);
  const [drafts, setDrafts] = useState<Jiaan1030ServiceDraft[]>([]);
  const [label, setLabel] = useState("");
  const [reviewers, setReviewers] = useState<GrantableReviewer[]>([]);
  const [rosterError, setRosterError] = useState(false);
  const [grants, setGrants] = useState<Record<string, ClientGrant[]>>({});
  const [grantMessage, setGrantMessage] = useState<Record<string, string>>({});
  const [grantInputs, setGrantInputs] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const loadGrants = (clientId: string) =>
    api<ClientGrant[]>(`/api/jiaan1030/service-clients/${clientId}/grants`, { cache: "no-store" })
      .then((rows) => setGrants((prev) => ({ ...prev, [clientId]: rows })))
      .catch(setError);

  const reload = () => {
    api<Jiaan1030ServiceClient[]>("/api/jiaan1030/service-clients").then(setClients).catch(setError);
  };

  useEffect(() => {
    reload();
    api<GrantableReviewer[]>("/api/jiaan1030/grantable-reviewers")
      .then((rows) => setReviewers(rows.filter((r) => r.id !== user.id)))
      .catch(() => setRosterError(true));
    api<Jiaan1030Catalog>("/api/jiaan1030/service-catalog")
      .then((c) => setApprovedForms(Array.isArray(c?.service_forms) ? c.service_forms : []))
      .catch(() => setApprovedForms([]));
    api<Jiaan1030ServiceDraft[]>("/api/jiaan1030/service-drafts", { cache: "no-store" })
      .then(setDrafts).catch(() => setDrafts([]));
  }, []);

  useEffect(() => {
    if (!clients) return;
    clients.filter((c) => c.created_by === user.id).forEach((c) => { void loadGrants(c.id); });
  }, [clients, user.id]);

  return (
    <div className="page stack">
      <h1>服務個案（測試用假資料）</h1>
      <div className="notice info">
        本頁僅供開發測試：請用假代稱（例如「測試個案甲」），不要輸入真實姓名、房號或其他個資。
      </div>
      <ErrorBox error={error} />
      <div className="card stack">
        <input placeholder="服務個案代稱（假資料）" value={label} onChange={(e) => setLabel(e.target.value)} />
        <button
          className="btn primary"
          disabled={busy || !label.trim()}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await post("/api/jiaan1030/service-clients", { display_label: label.trim() });
              setLabel("");
              reload();
            } catch (e) {
              setError(e);
            } finally {
              setBusy(false);
            }
          }}
        >
          新增服務個案
        </button>
      </div>
      <h2>我可存取的服務個案</h2>
      {clients === null ? (
        <p className="muted small">載入中…</p>
      ) : clients.length === 0 ? (
        <p className="muted small">尚無服務個案，請先新增一筆（假資料）。</p>
      ) : (
        clients.map((c) => (
          <div key={c.id} className="card stack">
            <strong>{c.display_label}</strong>
            {approvedForms.length === 0 ? (
              <p className="muted small">目前尚無已核准的服務紀錄表單（GA09/SC09），待主任核准後才會顯示於此。</p>
            ) : (
              <div className="row">
                {approvedForms.map((f) => {
                  const existing = drafts.find((d) => d.service_client_id === c.id && d.form_code === f.code);
                  if (!existing && user.role !== "caregiver") {
                    return <span key={f.code} className="tag" title="此身分僅唯讀，且目前尚無人填寫此表單">{f.code}：尚無人填寫</span>;
                  }
                  const label = existing
                    ? (existing.status === "submitted" ? `查看已送出的 ${f.code}` : `繼續填寫 ${f.code}（草稿）`)
                    : `填寫 ${f.title}（${f.code}）`;
                  return (
                    <Link key={f.code} className="btn" to={`/liff/service-clients/${c.id}/service-forms/${f.code}`}>
                      {label}
                    </Link>
                  );
                })}
              </div>
            )}
            {drafts.filter((d) => d.service_client_id === c.id).length > 0 && (
              <div className="small muted stack">
                <strong>此個案的表單紀錄</strong>
                <ul>
                  {drafts.filter((d) => d.service_client_id === c.id).map((d) => (
                    <li key={d.id}>
                      {d.form_code}｜{DRAFT_STATUS_LABEL[d.status] ?? d.status}｜
                      最後更新 {new Date(d.updated_at).toLocaleString("zh-TW")}
                      {d.created_by !== user.id && "（由其他已授權人員填寫）"}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {c.created_by === user.id && (
              <div className="stack">
                <p className="muted small">有效授權會列在下方；授權和撤銷後會立即更新。另一個帳號需重新整理才能看到變化。</p>
                {(grants[c.id] ?? []).filter((g) => !g.revoked_at).length === 0 ? (
                  <p className="muted small">目前沒有授權任何其他人存取此個案。</p>
                ) : (
                  <ul>{(grants[c.id] ?? []).filter((g) => !g.revoked_at).map((g) => (
                    <li key={g.id}>{g.grantee_name}（{g.grantee_username}）— 已授權</li>
                  ))}</ul>
                )}
                {grantMessage[c.id] && <p role="status" className="notice info">{grantMessage[c.id]}</p>}
              <div className="row">
                <select aria-label="選擇同機構督導或主任" value={grantInputs[c.id] ?? ""}
                  onChange={(e) => setGrantInputs({ ...grantInputs, [c.id]: e.target.value })}>
                  <option value="">選擇同機構督導／主任（測試帳號）</option>
                  {reviewers.map((r) => <option key={r.id} value={r.id}>
                    {r.display_name}（{r.username}）
                  </option>)}
                </select>
                {rosterError && <p className="notice warn">人員清單需要新版後端；目前先不要授權。</p>}
                <button
                  className="btn"
                  disabled={busy || rosterError || !grantInputs[c.id]?.trim()}
                  onClick={async () => {
                    setBusy(true);
                    setError(null);
                    try {
                      await post(`/api/jiaan1030/service-clients/${c.id}/grants`,
                        { grantee_id: grantInputs[c.id].trim() });
                      setGrantMessage((p) => ({ ...p, [c.id]: "授權已保存，請被授權帳號重新整理清單。" }));
                      await loadGrants(c.id);
                    } catch (e) {
                      setError(e);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  授權存取
                </button>
                <button
                  className="btn"
                  disabled={busy || rosterError || !grantInputs[c.id]?.trim()}
                  onClick={async () => {
                    setBusy(true);
                    setError(null);
                    try {
                      await api(`/api/jiaan1030/service-clients/${c.id}/grants/${grantInputs[c.id].trim()}/revoke`,
                        { method: "POST" });
                      setGrantMessage((p) => ({ ...p, [c.id]: "授權已撤銷；被撤銷帳號重新整理後不能再讀取此個案。" }));
                      await loadGrants(c.id);
                    } catch (e) {
                      setError(e);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  撤銷授權
                </button>
              </div>
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}
