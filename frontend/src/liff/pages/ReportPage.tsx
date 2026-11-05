import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, errorMessage, newRequestId, post, type CaseDetail, type Category } from "../../api";
import { ErrorBox } from "../components";

/** 分類快速回報：分類 → 常見問題 → 補充文字 → 確認送出。分類與模板來自後台設定。 */
export function ReportPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const preset = (location.state as { transcript_id?: string; summary?: string } | null) ?? null;
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [category, setCategory] = useState<Category | null>(null);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [text, setText] = useState(preset?.summary ?? "");
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [result, setResult] = useState<CaseDetail | null>(null);
  const requestId = useRef(newRequestId());

  const loadCategories = () => {
    setLoadError(null);
    setCategories(null);
    api<Category[]>("/api/categories").then(setCategories).catch(setLoadError);
  };
  useEffect(loadCategories, []);

  const submit = async () => {
    if (!category) return;
    setBusy(true);
    setError(null);
    try {
      const created = await post<CaseDetail>("/api/cases", {
        category_id: category.id,
        template_id: templateId,
        text,
        transcript_id: preset?.transcript_id ?? null,
        client_request_id: requestId.current,
      });
      setResult(created);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <div className="page stack">
        <div className="notice ok">
          <strong>案件已建立</strong>（案件 {result.number}，{result.status_label}）。
          {result.assignee ? `負責督導：${result.assignee.display_name}` : "尚未指派督導，可由本機構督導在待處理案件中查看。"}
        </div>
        <p className="small muted">案件建立不代表督導已讀取或回覆，請到「查看案件」確認。這也不等於已完成法定通報或機構正式異常事件程序。</p>
        <Link className="btn primary" to={`/liff/cases/${result.id}`}>查看案件</Link>
        <Link className="btn" to="/liff/report" onClick={() => { setResult(null); setStep(1); setCategory(null); setTemplateId(null); setText(""); requestId.current = newRequestId(); }}>再回報一件</Link>
        <Link className="btn block" to="/liff/report/entry">返回問題分類</Link>
      </div>
    );
  }

  return (
    <div className="page stack">
      <h1>問題分類回報</h1>
      <p className="notice warn" id="legacy-return-note">{busy ? '正在送交，請等候結果後再返回。' : '返回會離開此表單，未送出的選擇與補充不會保存。'}</p>
      <button className="btn block" disabled={busy} aria-describedby="legacy-return-note" onClick={() => navigate('/liff/report/entry')}>返回問題分類</button>
      <ErrorBox error={error} />
      {preset?.transcript_id && <div className="notice info">將附上已確認的談話摘要一併送交。</div>}
      {step === 1 && (
        <div className="stack">
          <p className="muted">① 選擇分類</p>
          {categories === null && !loadError && <p className="muted" role="status">分類與常見問題載入中…</p>}
          {!!loadError && <div className="notice danger" role="alert">
            {(loadError as { status?: number }).status === 403
              ? "權限不足，無法讀取分類與常見問題，請聯絡機構督導。"
              : (loadError as { status?: number }).status === 401
                ? "登入已失效，無法讀取分類與常見問題，請重新登入。"
                : "分類與常見問題載入失敗，請確認網路後重試。"}
            <button className="btn" onClick={loadCategories}>重新載入</button>
          </div>}
          {categories?.length === 0 && <p className="muted">目前沒有可用分類，請聯絡機構督導。</p>}
          {categories?.map((c) => (
            <button key={c.id} className="btn block" onClick={() => { setCategory(c); setTemplateId(null); setStep(2); }}>
              {c.name}
              {c.description && <span className="muted small">　{c.description}</span>}
            </button>
          ))}
        </div>
      )}
      {step === 2 && category && (
        <div className="stack">
          <p className="muted">② {category.name}：選擇常見問題（可略過）</p>
          {category.templates.length === 0 && <p className="muted">此分類目前沒有常見問題</p>}
          {category.templates.length === 0 && <p className="muted">可按「下一步」自行輸入問題，仍可送交督導。</p>}
          {category.templates.map((t) => (
            <button key={t.id} className={`btn block ${templateId === t.id ? "primary" : ""}`} onClick={() => setTemplateId(templateId === t.id ? null : t.id)}>{t.text}</button>
          ))}
          <div className="row">
            <button className="btn" onClick={() => setStep(1)}>上一步</button>
            <button className="btn primary" onClick={() => setStep(3)}>下一步</button>
          </div>
        </div>
      )}
      {step === 3 && category && (
        <div className="stack">
          <p className="muted">③ 補充說明（請用「個案」「家屬」代稱）</p>
          <div className="card small">
            <div><strong>{category.name}</strong></div>
            {templateId && <div>{category.templates.find((t) => t.id === templateId)?.text}</div>}
          </div>
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="請說明發生的情況，以及希望居督協助確認的問題；不要填姓名或政府個案案號" />
          {error ? <div className="notice danger">未能確認送出結果：{errorMessage(error)}。請先到「我的案件」確認；若需重試，請留在本頁再次送出，避免重複建案。<Link to="/liff/cases">查看我的案件</Link></div> : null}
          <div className="row">
            <button className="btn" onClick={() => setStep(2)} disabled={busy}>上一步</button>
            <button className="btn primary big" onClick={submit} disabled={busy || (!templateId && !text.trim())}>{busy ? "送交中…" : "確認送交督導確認"}</button>
          </div>
        </div>
      )}
    </div>
  );
}
