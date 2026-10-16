import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { useLiff } from "../LiffApp";

export function HomePage() {
  const { config, user } = useLiff();
  const [stats, setStats] = useState<{ open_cases: number; replied_cases: number } | null>(null);
  useEffect(() => {
    api<typeof stats>("/api/stats/mine").then(setStats).catch(() => setStats(null));
  }, []);
  return (
    <div className="page stack">
      <h1>{user.display_name}，您好</h1>
      <p className="muted">{user.org?.name}</p>
      <div className="notice info">
        對{config.bot_name}說「<strong>{config.wake_words[0]}</strong>，…」就能提問。請用「住民」「家屬」代稱，不要說姓名或房號。
      </div>
      <div className="menu-grid">
        <Link to="/liff/ask"><span className="icon">💬</span><strong>問 AI</strong><span className="muted small">文字或語音提問，回答附出處</span></Link>
        <Link to="/liff/record"><span className="icon">🎙️</span><strong>錄音／談話紀錄</strong><span className="muted small">多人談話轉文字、確認角色</span></Link>
        <Link to="/liff/report"><span className="icon">📋</span><strong>問題分類</strong><span className="muted small">點選分類，快速送交督導</span></Link>
        <Link to="/liff/cases"><span className="icon">📂</span><strong>我的案件</strong><span className="muted small">{stats ? `${stats.replied_cases} 件已回覆／${stats.open_cases} 件進行中` : "查看進度與督導回覆"}</span></Link>
        <Link to="/liff/help" style={{ gridColumn: "1 / -1" }}><span className="icon">📖</span><strong>使用說明與知識庫涵蓋範圍</strong></Link>
      </div>
    </div>
  );
}
