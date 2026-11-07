import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { useLiff } from "../LiffApp";

export function HomePage() {
  const { user } = useLiff();
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
        <Link to="/liff/ask"><span className="icon" aria-hidden="true">💬</span><strong>問 AI</strong><span className="muted">文字或語音提問，回答附出處</span></Link>
        <Link to="/liff/record"><span className="icon" aria-hidden="true">🎙️</span><strong>錄音／談話紀錄</strong><span className="muted">錄音後查看談話文字</span></Link>
        <Link to="/liff/report/entry"><span className="icon" aria-hidden="true">📋</span><strong>問題分類</strong><span className="muted">選擇試用預覽或原有分類回報</span></Link>
        <Link to="/liff/cases"><span className="icon" aria-hidden="true">📂</span><strong>我的案件</strong><span className="muted">{stats ? `${stats.replied_cases} 件已回覆／${stats.open_cases} 件進行中` : "查看進度與督導回覆"}</span></Link>
        {["caregiver", "supervisor", "director", "admin"].includes(user.role) && <a href="/api/jiaan1030/emergency-ui" className="emergency-entry" style={{ border: "2px solid #ad251e", borderRadius: 12, padding: 15, display: "grid", gap: 6, textDecoration: "none" }}><strong>🚨 緊急通報／督導接手</strong><span className="muted">僅網頁開啟時提示；危急先撥 119／110 並直接聯絡督導</span></a>}
        <Link to="/liff/service-clients"><span className="icon" aria-hidden="true">🧾</span><strong>服務紀錄表單</strong><span className="muted">GA09/SC09（測試用假資料）</span></Link>
      </div>
      <Link className="btn block home-help" to="/liff/help">使用說明與知識庫涵蓋範圍</Link>
    </div>
  );
}
