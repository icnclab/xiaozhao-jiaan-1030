import { Link, useLocation } from "react-router-dom";

export function ReportEntryPage() {
  const { state } = useLocation();
  return (
    <main className="page stack">
      <h1>問題分類</h1>
      <p>請選擇分類回報方式。</p>
      <section className="card stack" aria-label="點選分類回報">
        <Link className="btn primary block big" to="/liff/report/preview" state={state}>點選分類回報</Link>
        <p>點選問題類型、服務與原因，補充說明可不填；確認後送交居督。</p>
      </section>
      <section className="card stack" aria-label="原有分類回報">
        <Link className="btn block big" to="/liff/report" state={state}>原有分類回報</Link>
        <p>使用原本的分類、問題與送件流程。</p>
      </section>
      <a className="btn block" href="/api/jiaan1030/emergency-ui">🚨 嘉安緊急通報／督導接手（危急請先電話求援）</a>
      <Link className="btn block" to="/liff">返回首頁</Link>
    </main>
  );
}
