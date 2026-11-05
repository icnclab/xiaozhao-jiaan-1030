import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  isApiError,
  newRequestId,
  post,
  type Jiaan1030Catalog,
  type Jiaan1030ServiceDraft,
  type Jiaan1030ServiceForm,
} from "../../api";
import { ErrorBox } from "../components";
import { DynamicForm } from "../components/DynamicForm";
import { useLiff } from "../LiffApp";

const DEBOUNCE_MS = 800;

export function ServiceFormPage() {
  const { user } = useLiff();
  const { serviceClientId, code } = useParams();
  const [form, setForm] = useState<Jiaan1030ServiceForm | null>(null);
  const [draft, setDraft] = useState<Jiaan1030ServiceDraft | null>(null);
  const [readOnlyNoDraft, setReadOnlyNoDraft] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const createRequestId = useRef(newRequestId());
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!code) return;
    api<Jiaan1030Catalog>("/api/jiaan1030/service-catalog")
      .then((catalog) => {
        const found = catalog.service_forms.find((f) => f.code === code) ?? null;
        setForm(found);
      })
      .catch(setError);
  }, [code]);

  // 先找「這個個案＋這份表單」是否已有草稿（含已送出），有就直接接續／檢視，
  // 不要每次打開都另外建立一筆新的空白草稿。
  useEffect(() => {
    if (!serviceClientId || !code || !form) return;
    let active = true;
    api<Jiaan1030ServiceDraft[]>("/api/jiaan1030/service-drafts", { cache: "no-store" })
      .then((rows) => {
        if (!active) return;
        const existing = rows.find((d) => d.service_client_id === serviceClientId && d.form_code === code);
        if (existing) {
          setDraft(existing);
          return;
        }
        // 沒有既有草稿：只有建立者（照服員本人）能新建；被授權唯讀的督導／主任不嘗試建立。
        return post<Jiaan1030ServiceDraft>("/api/jiaan1030/service-drafts", {
          service_client_id: serviceClientId,
          form_code: code,
          payload: {},
          client_request_id: createRequestId.current,
        }).then((created) => { if (active) setDraft(created); })
          .catch((e) => {
            if (!active) return;
            if (isApiError(e) && e.status === 403) setReadOnlyNoDraft(true);
            else setError(e);
          });
      })
      .catch((e) => { if (active) setError(e); });
    return () => { active = false; };
  }, [serviceClientId, code, form]);

  const isOwner = Boolean(draft && draft.created_by === user.id);

  const scheduleSave = (next: Record<string, unknown>) => {
    if (!draft || !isOwner) return;
    setDraft({ ...draft, payload: next });
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      setSaving(true);
      try {
        const saved = await api<Jiaan1030ServiceDraft>(`/api/jiaan1030/service-drafts/${draft.id}`, {
          method: "PATCH",
          body: JSON.stringify({ payload: next }),
        });
        setDraft(saved);
      } catch (e) {
        setError(e);
      } finally {
        setSaving(false);
      }
    }, DEBOUNCE_MS);
  };

  if (!form) return <div className="page"><ErrorBox error={error} />{!error && <p className="muted">載入表單中…</p>}</div>;

  const approved = form.reviewed && form.schema_status === "approved";
  const sections = form.fields && "sections" in form.fields ? form.fields.sections : [];

  return (
    <div className="page stack">
      <p><Link to="/liff/service-clients">← 回服務個案列表</Link></p>
      <h1>{form.title}（{form.code}）</h1>
      {!approved && (
        <div className="notice warn">
          此表單尚未核准（{!form.reviewed ? "主任尚未正式核准" : "欄位內容尚未人工核對完成"}），僅供測試填寫，無法正式送出。
        </div>
      )}
      <ErrorBox error={error} />
      {readOnlyNoDraft && (
        <p className="notice info">此個案目前尚無人填寫過此表單，您目前對此個案僅有唯讀權限，無法建立新草稿。</p>
      )}
      {draft ? (
        <>
          {!isOwner && <p className="notice info">您正在檢視由其他人員建立的草稿／紀錄，依權限僅能瀏覽，欄位已鎖定。</p>}
          <DynamicForm sections={sections} payload={draft.payload} onChange={scheduleSave}
                      disabled={!isOwner || draft.status === "submitted"} />
          {isOwner && <p className="small muted">{saving ? "儲存中…" : "草稿已自動儲存"}</p>}
          {draft.status === "submitted" ? (
            <div className="notice ok">已正式送出（{new Date(draft.submitted_at ?? draft.updated_at).toLocaleString("zh-TW")}）。</div>
          ) : isOwner ? (
            <button
              className="btn primary"
              disabled={!approved || submitting}
              onClick={async () => {
                setSubmitting(true);
                setError(null);
                try {
                  setDraft(await post<Jiaan1030ServiceDraft>(`/api/jiaan1030/service-drafts/${draft.id}/submit`, {}));
                } catch (e) {
                  setError(e);
                } finally {
                  setSubmitting(false);
                }
              }}
            >
              送出
            </button>
          ) : (
            <p className="muted small">目前仍為草稿狀態，尚未送出。</p>
          )}
        </>
      ) : error || readOnlyNoDraft ? null : (
        <p className="muted">建立草稿中…</p>
      )}
    </div>
  );
}
