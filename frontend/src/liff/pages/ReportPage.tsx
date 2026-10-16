import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, errorMessage, newRequestId, post, type CaseDetail, type Category } from "../../api";
import { ErrorBox } from "../components";

/** 分類快速回報：分類 → 常見問題 → 補充文字 → 確認送出。分類與模板來自後台設定。 */
export function ReportPage() {
  const location = useLocation();
  const preset = (location.state as { transcript_id?: string; summary?: string } | null) ?? null;
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [category, setCategory] = useState<Category | null>(null);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [text, setText] = useState(preset?.summary ?? "");
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<CaseDetail | null>(null);
  const requestId = useRef(newRequestId());

  useEffect(() => {
    api<Category[]>("/api/categories").then(setCategories).catch(setError);
  }, []);

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
          <strong>已送交督導確認</strong>（案件 {result.number}，{result.status_label}）。
          {result.assignee ? `負責督導：${result.assignee.display_name}` : "尚未指派督導，將由機構共用待處理區接手。"}
        </div>
        <p className="small muted">這是送交督導確認，不等於已完成法定通報或機構正式異常事件程序。</p>
        <Link className="btn primary" to={`/liff/cases/${result.id}`}>查看案件</Link>
        <Link className="btn" to="/liff/report" onClick={() => { setResult(null); setStep(1); setCategory(null); setTemplateId(null); setText(""); requestId.current = newRequestId(); }}>再回報一件</Link>
      </div>
    );
  }

  return (
    <div className="page stack">
      <h1>問題分類回報</h1>
      <ErrorBox error={error} />
      {preset?.transcript_id && <div className="notice info">將附上已確認的談話摘要一併送交。</div>}
      {step === 1 && (
        <div className="stack">
          <p className="muted">① 選擇分類</p>
          {categories?.map((c) => (
            <button key={c.id} className="btn block" onClick={() => { setCategory(c); setStep(2); }}>
              {c.name}
              {c.description && <span className="muted small">　{c.description}</span>}
            </button>
          ))}
        </div>
      )}
      {step === 2 && category && (
        <div className="stack">
          <p className="muted">② {category.name}：選擇常見問題（可略過）</p>
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
          <p className="muted">③ 補充說明（請用「住民」「家屬」代稱）</p>
          <div className="card small">
            <div><strong>{category.name}</strong></div>
            {templateId && <div>{category.templates.find((t) => t.id === templateId)?.text}</div>}
          </div>
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="例如：家屬要求晚上多餵一次點心，住民有糖尿病紀錄，想確認能不能配合" />
          {error ? <div className="notice danger">送交失敗：{errorMessage(error)}。尚未轉交督導，請再試一次。</div> : null}
          <div className="row">
            <button className="btn" onClick={() => setStep(2)} disabled={busy}>上一步</button>
            <button className="btn primary big" onClick={submit} disabled={busy || (!templateId && !text.trim())}>{busy ? "送交中…" : "確認送交督導確認"}</button>
          </div>
        </div>
      )}
    </div>
  );
}
