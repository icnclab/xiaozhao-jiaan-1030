import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { post, setToken, type User } from "../../api";
import { ErrorBox } from "../../liff/components";

export function AdminLoginPage() {
  const { onLogin } = useOutletContext<{ onLogin: (u: User) => void }>();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="page stack" style={{ maxWidth: 420, paddingTop: 60 }}>
      <h1>督導後台登入</h1>
      <form
        className="card stack"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            const result = await post<{ session_token: string; user: User }>("/api/auth/login", { username, password });
            setToken(result.session_token);
            onLogin(result.user);
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <input type="text" placeholder="帳號" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        <input type="password" placeholder="密碼" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        <ErrorBox error={error} />
        <button className="btn primary" disabled={busy}>登入</button>
        <p className="small muted">展示帳號密碼在 F:\appdata\ltc_care\demo_accounts.txt（seed 時產生，不進版控）。</p>
      </form>
    </div>
  );
}
