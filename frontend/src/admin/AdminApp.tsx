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

  // 主任（director）後端目前僅有「案件監督（唯讀）」「治理指標」「人員查看」權限
  // （見 backend/app/api/admin_routes.py 的 CASE_OVERSIGHT／GOVERNANCE／STAFF_VIEW）；
  // 文件管理、問題分類設定、回答回饋未經會議紀錄確認，不在側邊選單提供入口，避免
  // 點擊後才被後端 403 擋下、誤以為系統故障。
  const DIRECTOR_HIDDEN_LINKS = new Set(["/admin/documents", "/admin/categories", "/admin/feedback"]);
  const links = [
    ["/admin/cases", "待確認案件"],
    ["/admin/documents", "知識庫文件"],
    ["/admin/categories", "問題分類"],
    ["/admin/feedback", "回答回饋"],
    ["/admin/metrics", "治理指標"],
    ["/admin/users", "帳號與綁定"],
  ].filter(([to]) => user.role !== "director" || !DIRECTOR_HIDDEN_LINKS.has(to));
  if (config.dev_features) links.push(["/admin/simulator", "LINE 模擬器"]);
  const roleLabel = user.role === "admin" ? "管理員" : user.role === "director" ? "主任" : "督導";
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
          <div style={{ padding: "0 10px 12px", fontWeight: 700 }}>督導後台</div>
          <div className="small" style={{ padding: "0 10px 12px", color: "#cfe8e5" }}>{user.display_name}（{roleLabel}）<br />{user.org?.name}</div>
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>{label}</NavLink>
          ))}
          <a href="#" onClick={(e) => { e.preventDefault(); logout(); }}>登出</a>
          <div className="small" style={{ padding: "12px 10px", color: "#9fc9c4" }}>
            模式：{Object.entries(config.modes).map(([k, v]) => `${k}=${v}`).join("、")}
          </div>
        </nav>
        <main>
          {config.line_mode === "mock" && <div className="mode-banner">LINE 為模擬模式：通知與訊息不會送到真實 LINE</div>}
          <Outlet />
        </main>
      </div>
    </AdminContext.Provider>
  );
}
