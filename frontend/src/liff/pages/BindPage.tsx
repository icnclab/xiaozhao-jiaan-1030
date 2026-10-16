import { useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import type { PublicConfig, User } from "../../api";
import { bindWithCode } from "../auth";
import { ErrorBox } from "../components";

export function BindPage() {
  const ctx = useOutletContext<{ config: PublicConfig; idToken: string; onBound: (u: User) => void } | undefined>();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const navigate = useNavigate();
  if (!ctx) {
    return <div className="page"><div className="notice ok">此 LINE 帳號已綁定，請回首頁。</div></div>;
  }
  return (
    <div className="page stack">
      <h1>綁定帳號</h1>
      <p>請輸入督導或管理員提供的 8 碼綁定碼，把您的 LINE 與機構帳號連結。</p>
      <input type="text" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="例如 AB3K7X9P" maxLength={8} autoCapitalize="characters" />
      <ErrorBox error={error} />
      <button
        className="btn primary big block"
        disabled={busy || code.length < 6}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            const user = await bindWithCode(ctx.idToken, code);
            ctx.onBound(user);
            navigate("/liff", { replace: true });
          } catch (e) {
            setError(e);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "綁定中…" : "綁定"}
      </button>
    </div>
  );
}
