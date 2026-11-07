import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, errorMessage, getToken, isApiError, setToken, type PublicConfig, type User } from "../api";
import { loginDev, loginWithLiff, reopenLiff, type LiffSession } from "./auth";

interface LiffContextValue {
  config: PublicConfig;
  user: User;
  dev: boolean;
  logout: () => void;
}

const LiffContext = createContext<LiffContextValue | null>(null);

export function useLiff(): LiffContextValue {
  const value = useContext(LiffContext);
  if (!value) throw new Error("LiffContext missing");
  return value;
}

/** 綁定頁需要的暫存：尚未綁定的 ID token（只在記憶體）。 */
export const pendingBinding: { idToken: string | null } = { idToken: null };

interface DevUser {
  username: string;
  display_name: string;
  line_user_id: string | null;
  blocked: boolean;
}

function DevLogin({ onPick }: { onPick: (lineUserId: string) => void }) {
  const [users, setUsers] = useState<DevUser[]>([]);
  useEffect(() => {
    api<DevUser[]>("/api/dev/line/users").then(setUsers).catch(() => setUsers([]));
  }, []);
  return (
    <div className="page stack">
      <div className="mode-banner">模擬模式：未串接真實 LINE，以下登入為開發用假身分</div>
      <h1>選擇模擬照服員</h1>
      {users.map((u) => (
        <button
          key={u.username}
          className="btn block"
          onClick={() => onPick(u.line_user_id ?? `U${u.username.padEnd(32, "0").slice(0, 32)}`)}
        >
          {u.display_name}（{u.username}）{u.line_user_id ? "" : "－未綁定，會進綁定流程"}
        </button>
      ))}
      <p className="muted">真實 LINE 環境會改由 LIFF SDK 取得 ID token，並由後端向 LINE 驗證。</p>
    </div>
  );
}

export function LiffApp() {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [session, setSession] = useState<LiffSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    api<PublicConfig>("/api/config/public").then(setConfig).catch((e) => setError(errorMessage(e)));
  }, []);

  // 已有 session token → 直接取 /me
  useEffect(() => {
    if (!config || session) return;
    let cancelled = false;
    setBusy(true);
    async function restore() {
      if (getToken()) {
        try {
          const user = await api<User>("/api/me");
          if (!cancelled) { setBusy(false); setSession({ status: "ok", user, dev: config!.line_mode === "mock" }); }
          return;
        } catch (e) {
          // Only an expired/invalid application session may trigger fresh LINE verification.
          if (!isApiError(e) || e.status !== 401) throw e;
          if (cancelled) return;
          setToken(null);
        }
      }
      if (!cancelled && config!.line_mode === "real" && config!.liff_id) {
        const next = await loginWithLiff(config!);
        if (!cancelled) { setBusy(false); setSession(next); }
      }
    }
    restore().catch((e) => {
      if (!cancelled) setError(errorMessage(e));
    }).finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [config, session]);

  useEffect(() => {
    if (session?.status === "needs_binding") {
      pendingBinding.idToken = session.idToken;
    }
  }, [session, navigate, location.pathname]);

  const logout = useCallback(() => {
    api("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    setToken(null);
    setSession(null);
  }, []);

  if (error) {
    return (
      <div className="page">
        <div className="notice danger">{error}</div>
        <button className="btn block" onClick={() => window.location.reload()}>重新載入</button>
        {config?.line_mode === "real" && config.liff_id && (
          <button className="btn block" onClick={() => {
            setError(null); setBusy(true);
            reopenLiff(config).catch((e) => { setError(errorMessage(e)); setBusy(false); });
          }}>重新進行 LINE 登入</button>
        )}
      </div>
    );
  }
  if (!config || busy) return <div className="page muted">載入中…</div>;
  if (!session) {
    if (config.dev_features) {
      return <DevLogin onPick={(id) => loginDev(id).then(setSession).catch((e) => setError(errorMessage(e)))} />;
    }
    return <div className="page notice warn">尚未設定 LIFF（LIFF_ID／LINE_LOGIN_CHANNEL_ID），無法登入。</div>;
  }
  if (session.status === "needs_binding") {
    // Protected pages must not mount without LiffContext while redirecting.
    if (location.pathname !== "/liff/bind") return <Navigate to="/liff/bind" replace />;
    return (
      <Outlet context={{ config, idToken: session.idToken, onBound: (user: User) => setSession({ status: "ok", user, dev: session.dev }) }} />
    );
  }

  const tabs = [
    { to: "/liff", label: "首頁", icon: "🏠", end: true },
    { to: "/liff/ask", label: "問 AI", icon: "💬" },
    { to: "/liff/record", label: "錄音", icon: "🎙️" },
    { to: "/liff/report/entry", label: "問題分類", icon: "📋" },
    { to: "/liff/cases", label: "我的案件", icon: "📂" },
  ];
  const mockModes = Object.entries(config.modes).filter(([, v]) => v === "mock" || v === "extractive");
  return (
    <LiffContext.Provider value={{ config, user: session.user, dev: session.dev, logout }}>
      {(session.dev || mockModes.length > 0) && (
        <div className="mode-banner">
          {session.dev ? "模擬登入" : ""}
          {mockModes.length > 0 ? `　模擬／退路模式：${mockModes.map(([k, v]) => `${k}=${v}`).join("、")}` : ""}
        </div>
      )}
      <div className="topbar">
        <NavLink to="/liff"><strong>{config.bot_name}｜長照 AI 照護小幫手</strong></NavLink>
        <span className="small">{session.user.display_name}</span>
      </div>
      <div className="page"><NavLink to="/liff/mpc-review" className="btn">MPC 人工核對（測試）</NavLink></div>
      <Outlet />
      <nav className="tabbar">
        {tabs.map((t) => (
          <NavLink key={t.to} to={t.to} end={t.end} className={({ isActive }) => ((t.to === "/liff/report/entry" ? location.pathname === "/liff/report" || location.pathname.startsWith("/liff/report/") : isActive) ? "active" : "")}>
            <span className="icon">{t.icon}</span>
            {t.label}
          </NavLink>
        ))}
      </nav>
    </LiffContext.Provider>
  );
}
