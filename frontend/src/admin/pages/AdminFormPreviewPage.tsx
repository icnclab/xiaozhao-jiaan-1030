import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  newRequestId,
  post,
  type Jiaan1030Catalog,
  type Jiaan1030ServiceClient,
  type Jiaan1030ServiceDraft,
  type Jiaan1030ServiceForm,
} from "../../api";
import { ErrorBox } from "../../liff/components";
import { DynamicForm } from "../../liff/components/DynamicForm";
import { useAdmin } from "../AdminApp";

const DEBOUNCE_MS = 800;
const PREVIEW_CLIENT_LABEL = "管理員預覽測試個案（虛構，僅供表單預覽，非真實服務對象）";

/**
 * 未核准表單的真實欄位預覽：給主任／督導／管理員用既有「服務分類核准」頁的唯讀權限
 * （/api/jiaan1030/service-catalog/review），實際操作尚未核准的 DynamicForm，
 * 並用管理員自己建立的虛構測試個案（既有草稿 API、既有授權規則：建立者本來就可讀寫自己的草稿）
 * 驗證暫存／重新開啟，不開放一般照服員使用、不加入正式服務清單、不自動核准。
 */
export function AdminFormPreviewPage() {
  const { user } = useAdmin();
  const { code } = useParams();
  const [form, setForm] = useState<Jiaan1030ServiceForm | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [draft, setDraft] = useState<Jiaan1030ServiceDraft | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const createRequestId = useRef(newRequestId());
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!code) return;
    api<Jiaan1030Catalog>("/api/jiaan1030/service-catalog/review")
      .then((catalog) => {
        const found = catalog.service_forms.find((f) => f.code === code) ?? null;
        if (!found) { setNotFound(true); return; }
        setForm(found);
      })
      .catch(setError);
  }, [code]);

  useEffect(() => {
    if (!form) return;
    let active = true;
    (async () => {
      try {
        const clients = await api<Jiaan1030ServiceClient[]>("/api/jiaan1030/service-clients", { cache: "no-store" });
        let client = clients.find((c) => c.display_label === PREVIEW_CLIENT_LABEL) ?? null;
        if (!client) {
          client = await post<Jiaan1030ServiceClient>("/api/jiaan1030/service-clients", { display_label: PREVIEW_CLIENT_LABEL });
        }
        if (!active || !client) return;
        const drafts = await api<Jiaan1030ServiceDraft[]>("/api/jiaan1030/service-drafts", { cache: "no-store" });
        const existing = drafts.find((d) => d.service_client_id === client!.id && d.form_code === form.code);
        if (existing) { setDraft(existing); return; }
        const created = await post<Jiaan1030ServiceDraft>("/api/jiaan1030/service-drafts", {
          service_client_id: client.id, form_code: form.code, payload: {}, client_request_id: createRequestId.current,
        });
        if (active) setDraft(created);
      } catch (e) {
        if (active) setError(e);
      }
    })();
    return () => { active = false; };
  }, [form]);

  const scheduleSave = (next: Record<string, unknown>) => {
    if (!draft) return;
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

  if (notFound) return <div className="notice danger">找不到此表單代碼。</div>;
  if (!form) return <div><ErrorBox error={error} />{!error && <p className="muted">載入中…</p>}</div>;

  const approved = form.reviewed && form.schema_status === "approved";
  const sections = form.fields && "sections" in form.fields ? form.fields.sections : [];

  return (
    <div className="stack">
      <p><Link to="/admin/catalog">← 回服務分類核准</Link></p>
      <h1>{form.title}</h1>
      <div className={`notice ${approved ? "ok" : "warn"}`}>
        {approved
          ? `✅ 此表單（${form.code}）已核准，可正式使用；以下仍為管理員測試預覽，不影響正式送出流程。`
          : `🔧 展示測試／尚未核准：此表單（${form.code}）尚未經嘉安核准，僅供主任／督導／系統管理員（${user.display_name}）
             在此頁面預覽與測試填寫；一般照服員看不到此代碼，正式服務清單也不會出現此表單。所有欄位皆為虛構測試資料。`}
      </div>
      <ErrorBox error={error} />
      {draft ? (
        <>
          <DynamicForm sections={sections} payload={draft.payload} onChange={scheduleSave}
                      disabled={draft.status === "submitted"} />
          <p className="small muted">{saving ? "儲存中…" : "測試草稿已自動暫存；重新整理或離開後再回來會保留上次內容（重新開啟）。"}</p>
          {!approved && (
            <div className="notice info small">
              此為未核准表單，依安全規則一律禁止正式送出——不是系統故障。需先由主任／系統管理員在「服務分類核准」頁核准此表單，才能對正式代碼開放送出。
            </div>
          )}
        </>
      ) : <p className="muted">建立預覽測試草稿中…</p>}
    </div>
  );
}
