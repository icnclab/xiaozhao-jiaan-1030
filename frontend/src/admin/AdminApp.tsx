import { createContext, useContext, useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, getToken, setToken, type PublicConfig, type User } from "../api";

interface AdminContextValue {
  user: User;
  config: PublicConfig;
  logout: () => void;
}

const AdminContext = createContext<AdminContextValue | null>(null);

export function useAdmin(): AdminContextValue {
  const value = useContext(AdminContext);
  if (!value) throw new Error("AdminContext missing");
  return value;
}

interface CaseRow { id: string; status: string; assignee: string | null }

interface CaseCounts {
  /** status=pending 且 assignee 為空：真正沒人認領、可以直接接手。 */
  unassignedPending: number;
  /** status=pending 但已指派：還沒開始處理（尚未按「接手」），不是「待接手」。 */
  assignedPending: number;
  /** status=in_progress（take() 一定會同時指派，故處理中必有人）。 */
  inProgress: number;
  /** 指派給目前登入者、尚未結案／回覆的案件。 */
  mine: number;
}

/** 首頁統計方塊的案件數字；用既有 /api/admin/cases 清單端點算數，不新增後端 API。
 * 準確區分「未指派待接手」與「已指派但尚未處理」，不得把兩者混算成同一個「待接手」數字。 */
function useCaseCounts(): CaseCounts | null {
  const [counts, setCounts] = useState<CaseCounts | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([
      api<CaseRow[]>("/api/admin/cases?status=pending", { cache: "no-store" }),
      api<CaseRow[]>("/api/admin/cases?status=in_progress", { cache: "no-store" }),
      api<CaseRow[]>("/api/admin/cases?status=pending,in_progress&mine=true", { cache: "no-store" }),
    ]).then(([pending, inProgress, mine]) => {
      if (!active) return;
      const unassignedPending = pending.filter((r) => !r.assignee).length;
      setCounts({
        unassignedPending,
        assignedPending: pending.length - unassignedPending,
        inProgress: inProgress.length,
        mine: mine.length,
      });
    }).catch(() => { if (active) setCounts(null); });
    return () => { active = false; };
  }, []);
  return counts;
}

const NAV_GROUPS: { title: string; links: [string, string][] }[] = [
  { title: "案件管理", links: [
    ["/admin/cases", "案件列表與回報"],
    ["/liff/service-clients", "服務個案與授權（測試）"],
  ] },
  { title: "服務表單", links: [
    ["/admin/categories", "問題分類設定"],
    ["/admin/catalog", "BA／GA09／SC09 核准"],
  ] },
  { title: "知識庫", links: [
    ["/liff/ask", "法規查詢（問 AI）"],
    ["/admin/documents", "知識庫文件"],
  ] },
  { title: "系統管理", links: [
    ["/admin/feedback", "回答回饋"],
    ["/admin/metrics", "治理指標"],
    ["/admin/users", "帳號與綁定"],
  ] },
];

// 主任（director）後端目前僅有「案件監督（唯讀）」「治理指標」「人員查看」權限；
// 文件管理、回答回饋、問題分類設定未經會議紀錄確認，不在側邊選單提供入口，
// 避免點擊後才被後端 403 擋下、誤以為系統故障。見 backend/app/api/admin_routes.py
// 的 CASE_OVERSIGHT／GOVERNANCE／STAFF_VIEW。
const DIRECTOR_HIDDEN_LINKS = new Set(["/admin/documents", "/admin/feedback", "/admin/categories"]);
function navGroupsForRole(role: string): typeof NAV_GROUPS {
  if (role !== "director") return NAV_GROUPS;
  return NAV_GROUPS.map((g) => ({ ...g, links: g.links.filter(([to]) => !DIRECTOR_HIDDEN_LINKS.has(to)) }))
    .filter((g) => g.links.length > 0);
}

export function AdminApp() {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    let active = true;
    api<PublicConfig>("/api/config/public").then((c) => { if (active) setConfig(c); }).catch(() => { if (active) setConfig(null); });
    if (!getToken()) {
      setUser(null);
      return () => { active = false; };
    }
    api<User>("/api/me")
      .then((u) => { if (active) setUser(u.role === "caregiver" ? null : u); })
      .catch(() => {
        if (!active) return;
        setToken(null);
        setUser(null);
      });
    return () => { active = false; };
  }, []);

  if (user === undefined || !config) return <div className="page muted">載入中…</div>;
  if (user === null) {
    // Never render protected children after removing their context provider.
    if (location.pathname !== "/admin/login") return <Navigate to="/admin/login" replace />;
    return <Outlet context={{ onLogin: (u: User) => { setUser(u); navigate("/admin/cases", { replace: true }); } }} />;
  }
  if (location.pathname === "/admin/login") return <Navigate to="/admin/cases" replace />;

  const groups = navGroupsForRole(user.role).map((g) => ({ ...g, links: g.links.slice() }));
  const systemGroup = groups[groups.length - 1];
  if (user.role === "admin") systemGroup.links.push(["/admin/audit", "稽核紀錄"]);
  if (config.dev_features) systemGroup.links.push(["/admin/simulator", "LINE 模擬器"]);
  const roleLabels: Record<string, string> = { admin: "管理員", director: "主任", supervisor: "居督" };
  const workspaceTitles: Record<string, string> = { admin: "系統管理工作台", director: "主任管理工作台", supervisor: "居督管理工作台" };
  const roleLabel = roleLabels[user.role] ?? user.role;
  const workspaceTitle = workspaceTitles[user.role] ?? "管理工作台";
  const logout = () => {
    api("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    setToken(null);
    setUser(null);
    navigate("/admin/login", { replace: true });
  };
  return (
    <AdminContext.Provider value={{ user, config, logout }}>
      <div className="admin">
        <nav>
          <div className="nav-brand">{workspaceTitle}</div>
          <div className="nav-who small">{user.display_name}（{roleLabel}）<br />{user.org?.name}</div>
          {groups.map((g) => (
            <div className="nav-section" key={g.title}>
              <div className="nav-section-title">{g.title}</div>
              {g.links.map(([to, label]) => (
                <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>{label}</NavLink>
              ))}
            </div>
          ))}
          <a className="nav-logout" href="#" onClick={(e) => { e.preventDefault(); logout(); }}>登出</a>
          {config.dev_features && (
            <details className="nav-devinfo">
              <summary>系統資訊（僅開發模式）</summary>
              <div className="small">模式：{Object.entries(config.modes).map(([k, v]) => `${k}=${v}`).join("、")}</div>
            </details>
          )}
        </nav>
        <main>
          {user.role === "supervisor" && <SupervisorHome />}
          {user.role === "director" && <DirectorHome />}
          {user.role === "admin" && <AdminHome />}
          {config.line_mode === "mock" && <div className="mode-banner">LINE 為模擬模式：通知與訊息不會送到真實 LINE</div>}
          <Outlet />
        </main>
      </div>
    </AdminContext.Provider>
  );
}

/** 居督首頁：以每日要處理的案件為中心。 */
function SupervisorHome() {
  const counts = useCaseCounts();
  return (
    <section className="card workspace-card" aria-label="居督核心工作區">
      <h2>今日待處理</h2>
      <p>個案資料仍依授權顯示，權限不因本頁增加而擴張；跨居督共享案件須有明確授權才看得到。</p>
      <div className="stat-grid">
        <NavLink className="stat-tile urgent" to="/admin/cases?status=pending&unassigned=true">
          <span className="stat-label">待接手（未指派）</span>
          <span className="stat-value">{counts ? counts.unassignedPending : "…"}</span>
        </NavLink>
        <NavLink className="stat-tile" to="/admin/cases?status=pending">
          <span className="stat-label">已指派待處理</span>
          <span className="stat-value">{counts ? counts.assignedPending : "…"}</span>
        </NavLink>
        <NavLink className="stat-tile" to="/admin/cases?status=in_progress">
          <span className="stat-label">處理中案件</span>
          <span className="stat-value">{counts ? counts.inProgress : "…"}</span>
        </NavLink>
        <NavLink className="stat-tile" to="/admin/cases?status=pending,in_progress&mine=true">
          <span className="stat-label">我的案件</span>
          <span className="stat-value">{counts ? counts.mine : "…"}</span>
        </NavLink>
      </div>
      <div className="action-grid">
        <NavLink className="btn" to="/admin/cases">案件回覆／接手／結案</NavLink>
        <NavLink className="btn" to="/liff/service-clients">跨居督共享個案（測試）</NavLink>
        <NavLink className="btn" to="/admin/users">檢視人員帳號與綁定</NavLink>
        <a className="btn danger" href="/api/jiaan1030/emergency-ui">🚨 緊急事件入口</a>
      </div>
      <p className="small">緊急事件請依現場通報及電話求援流程處理；此頁不代表背景 APP 警報已完成。</p>
    </section>
  );
}

/** 主任首頁：以管理與監督為中心。 */
function DirectorHome() {
  const counts = useCaseCounts();
  return (
    <section className="card workspace-card" aria-label="主任核心工作區">
      <h2>機構監督總覽</h2>
      <p>主任負責機構業務管理（人員與角色、案件監督、服務分類核准），與系統管理員的技術設定／帳號維運權限分開設計。</p>
      <div className="stat-grid">
        <NavLink className="stat-tile urgent" to="/admin/cases?status=pending&unassigned=true">
          <span className="stat-label">待審核（未指派）</span>
          <span className="stat-value">{counts ? counts.unassignedPending : "…"}</span>
        </NavLink>
        <NavLink className="stat-tile" to="/admin/cases?status=pending">
          <span className="stat-label">已指派待處理</span>
          <span className="stat-value">{counts ? counts.assignedPending : "…"}</span>
        </NavLink>
        <NavLink className="stat-tile" to="/admin/cases?status=in_progress">
          <span className="stat-label">處理中案件</span>
          <span className="stat-value">{counts ? counts.inProgress : "…"}</span>
        </NavLink>
      </div>
      <div className="action-grid">
        <NavLink className="btn" to="/admin/users">人員與角色管理</NavLink>
        <NavLink className="btn" to="/admin/catalog">BA／GA09／SC09 核准</NavLink>
        <NavLink className="btn" to="/admin/cases">跨居督案件監督</NavLink>
        <NavLink className="btn" to="/admin/metrics">治理指標</NavLink>
        <a className="btn danger" href="/api/jiaan1030/emergency-ui">🚨 緊急事件管理</a>
      </div>
      <p className="small">稽核紀錄目前僅限系統管理員查看；如需主任也能查看，須先經嘉安確認權限範圍。</p>
    </section>
  );
}

function AdminHome() {
  return (
    <details className="card workspace-card">
      <summary>系統管理導覽</summary>
      <p>技術管理與內容治理；不代替主任監督業務。</p>
      <div className="action-grid">
        {[["/admin/users", "帳號管理"], ["/admin/documents", "知識庫與文件版本"], ["/admin/feedback", "AI 回答有誤審核"],
          ["/admin/metrics", "治理指標與系統紀錄"], ["/admin/audit", "稽核紀錄"]].map(([to, label]) => (
          <NavLink className="btn" key={to} to={to}>{label}</NavLink>
        ))}
        <a className="btn" href="/api/fieldtest/dashboard">47 人場測管理（受測者對應／統計／匯出）</a>
      </div>
      <p className="small">系統即時健康資訊未由此頁提供。回饋須經人工審核，不會自動訓練 AI。場測資料表尚未建立前，場測頁會顯示明確提示，不是系統故障。</p>
    </details>
  );
}
