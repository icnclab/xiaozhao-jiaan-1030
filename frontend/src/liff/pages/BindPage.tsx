import { useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import type { PublicConfig, User } from "../../api";
import { bindWithCode } from "../auth";
import { normalizeBindingCode, validBindingCode } from "../bindingCode";
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
      <p>請輸入 8 碼綁定碼，將「本人」的 LINE 與機構帳號連結。照服員可向督導領取；督導、主任及管理員需由具權限的人員在後台核發。</p>
      {/* XZ_MANAGER_LINE_BINDING_20261103：綁定的是 LINE 身分，不更改資料庫中的角色。 */}
      <label htmlFor="binding-code">8 碼綁定碼</label>
      <input id="binding-code" type="text" value={code}
        onChange={(e) => setCode(normalizeBindingCode(e.target.value))}
        onPaste={(e) => {
          e.preventDefault();
          const input = e.currentTarget;
          const start = input.selectionStart ?? 0;
          const end = input.selectionEnd ?? code.length;
          setCode(normalizeBindingCode(code.slice(0, start) + e.clipboardData.getData("text") + code.slice(end)));
        }}
        placeholder="例如 AB3K7X9P" autoCapitalize="characters" autoCorrect="off" spellCheck={false}
        aria-describedby="binding-code-help" aria-invalid={Boolean(code && !validBindingCode(code))} />
      <p id="binding-code-help">可手動輸入或貼上，空白與換行會自動整理。請輸入完整 8 碼英文字母及數字。</p>
      {code && !validBindingCode(code) && <p role="status">綁定碼格式不正確，請確認完整 8 碼，不含標點符號。</p>}
      <ErrorBox error={error} />
      <button
        className="btn primary big block"
        disabled={busy || !validBindingCode(code)}
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
