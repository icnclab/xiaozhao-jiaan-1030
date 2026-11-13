import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { useLiff } from "../LiffApp";

export function HomePage() {
  const { user, dev } = useLiff();
  const [stats, setStats] = useState<{ open_cases: number; replied_cases: number } | null>(null);
  useEffect(() => {
    api<typeof stats>("/api/stats/mine").then(setStats).catch(() => setStats(null));
  }, []);
  return (
    <div className="page stack">
      <h1>{user.display_name}，您好</h1>
      <p className="muted">{user.org?.name}</p>
      <div className="notice info">
        請選一項功能開始。填寫或說明時，請用「個案」「家屬」代稱，不要提供姓名或房號。
      </div>
      {/* XZ_EMERGENCY_ROLE_ENTRY_20261103: the server enforces org and role authorization. */}
      <div className="menu-grid">
        {/* 督導/主任用專屬督導AI助手（/api/qa/supervisor-ask 後端角色檢查），不是照服員那套/liff/ask */}
        {["supervisor", "director", "admin"].includes(user.role) ? (
          <Link to="/liff/supervisor-ask"><span className="icon" aria-hidden="true">💬</span><strong>AI 照護助手</strong><span className="muted">預設語音提問，回答附出處</span></Link>
        ) : (
          <Link to="/liff/ask"><span className="icon" aria-hidden="true">💬</span><strong>問 AI</strong><span className="muted">文字或語音提問，回答附出處</span></Link>
        )}
        <Link to="/liff/record"><span className="icon" aria-hidden="true">🎙️</span><strong>錄音／談話紀錄</strong><span className="muted">錄音後查看談話文字</span></Link>
        <Link to="/liff/report/entry"><span className="icon" aria-hidden="true">📋</span><strong>問題分類</strong><span className="muted">選擇試用預覽或原有分類回報</span></Link>
        <Link to="/liff/cases"><span className="icon" aria-hidden="true">📂</span><strong>我的案件</strong><span className="muted">{stats ? `${stats.replied_cases} 件已回覆／${stats.open_cases} 件進行中` : "查看進度與督導回覆"}</span></Link>
        {/* 統一指向當前正式版 SOS App；443 與 8443 不共用瀏覽器登入狀態。 */}
        {["caregiver", "supervisor", "director", "admin"].includes(user.role) && <a target="_blank" rel="noopener noreferrer" href="https://stust.tail379935.ts.net:8443/api/jiaan1030/sos-app/" className="emergency-entry" style={{ border: "2px solid #ad251e", borderRadius: 12, padding: 15, display: "grid", gap: 6, textDecoration: "none" }}><strong>🚨 新分頁開啟緊急通報／督導接手</strong><span className="muted">LINE若未開啟新分頁，請長按並選擇外部瀏覽器；網址可複製。危急請先撥 119／110。</span></a>}
        {/* GA09/SC09 尚未經嘉安確認為正式上線功能，正式畫面先隱藏，僅保留於模擬登入／測試入口 */}
        {dev && <Link to="/liff/service-clients"><span className="icon" aria-hidden="true">🧾</span><strong>服務紀錄表單</strong><span className="muted">GA09/SC09（測試用假資料）</span></Link>}
      </div>
      <Link className="btn block home-help" to="/liff/help">使用說明與知識庫涵蓋範圍</Link>
    </div>
  );
}
