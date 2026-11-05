import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, post, type Jiaan1030Catalog } from "../../api";
import { ErrorBox } from "../../liff/components";
import { useAdmin } from "../AdminApp";

export function AdminCatalogPage() {
  const { user } = useAdmin();
  const [catalog, setCatalog] = useState<Jiaan1030Catalog | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const canApprove = user.role === "director" || user.role === "admin";

  const reload = () => {
    api<Jiaan1030Catalog>("/api/jiaan1030/service-catalog/review").then(setCatalog).catch(setError);
  };
  useEffect(reload, []);

  const toggleBa = async (code: string, reviewed: boolean) => {
    setBusy(code);
    try {
      await post(`/api/jiaan1030/ba-services/${code}/approve`, { reviewed });
      reload();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const toggleForm = async (code: string, approve: boolean) => {
    setBusy(code);
    try {
      // 核准時一併確認 schema_status=approved：欄位結構本身另由工程端套用，
      // 這裡只負責「主任核准」這個業務動作，不會改寫欄位內容。
      await post(`/api/jiaan1030/service-forms/${code}/approve`,
                approve ? { schema_status: "approved", reviewed: true } : { reviewed: false });
      reload();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  if (!catalog) return <div><ErrorBox error={error} />{!error && <p className="muted">載入中…</p>}</div>;

  return (
    <div className="stack">
      <h1>服務分類核准（BA／GA09／SC09）</h1>
      <p className="small muted">
        {canApprove
          ? "核准只切換「是否已由嘉安確認」的旗標，不會自動修改名稱、代碼或表單欄位內容；核准前欄位仍標示「待核對」。"
          : "僅主任／系統管理員可以核准；督導可檢視目前核准狀態。"}
      </p>
      <ErrorBox error={error} />

      <div className="card">
        <h2>BA 服務項目（{catalog.ba_services.length} 項）</h2>
        <table>
          <thead><tr><th>代碼</th><th>名稱</th><th>狀態</th>{canApprove && <th>操作</th>}</tr></thead>
          <tbody>
            {catalog.ba_services.map((b) => (
              <tr key={b.code}>
                <td>{b.code}</td>
                <td>{b.name}</td>
                <td>{b.reviewed ? <span className="tag ok">已核准</span> : <span className="tag warn">待核准</span>}</td>
                {canApprove && (
                  <td>
                    <button className="btn" disabled={busy === b.code} onClick={() => toggleBa(b.code, !b.reviewed)}>
                      {b.reviewed ? "撤銷核准" : "核准"}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>服務紀錄表單（GA09／SC09）</h2>
        <table>
          <thead><tr><th>代碼</th><th>標題</th><th>欄位結構</th><th>核准狀態</th>{canApprove && <th>操作</th>}</tr></thead>
          <tbody>
            {catalog.service_forms.map((f) => {
              const hasFields = "sections" in f.fields && f.fields.sections.length > 0;
              const approved = f.reviewed && f.schema_status === "approved";
              return (
                <tr key={f.code}>
                  <td>{f.code}</td>
                  <td>{f.title}</td>
                  <td>
                    {hasFields ? `${f.fields.sections.length} 個區塊` : "尚未設定欄位（工程端尚未套用，無法核准）"}
                    {hasFields && <><br /><Link to={`/admin/catalog/preview/${f.code}`}>預覽真實表單（展示測試）</Link></>}
                  </td>
                  <td>
                    {approved
                      ? <span className="tag ok">已核准，可正式送出</span>
                      : <span className="tag warn">待核准（{f.schema_status ?? "draft_unverified"}）</span>}
                  </td>
                  {canApprove && (
                    <td>
                      <button className="btn" disabled={busy === f.code || (!approved && !hasFields)}
                              onClick={() => toggleForm(f.code, !approved)}>
                        {approved ? "撤銷核准" : "核准"}
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
