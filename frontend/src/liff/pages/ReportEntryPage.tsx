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
      {/* 統一指向當前正式版 SOS App；443 與 8443 不共用瀏覽器登入狀態。 */}
      <a className="btn block" target="_blank" rel="noopener noreferrer" href="https://stust.tail379935.ts.net:8443/api/jiaan1030/sos-app/">🚨 新分頁開啟嘉安緊急通報／督導接手</a><p className="small muted">LINE若未開啟新分頁，請長按連結選擇「使用外部瀏覽器開啟」，或複製網址：https://stust.tail379935.ts.net:8443/api/jiaan1030/sos-app/</p>
      <Link className="btn block" to="/liff">返回首頁</Link>
    </main>
  );
}
