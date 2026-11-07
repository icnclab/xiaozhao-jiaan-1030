/**
 * LIFF 身分：只把 ID token 交給後端驗證；前端不決定 user_id 或角色。
 * 模擬模式（後端 dev_features=true）改用 `dev:<LINE userId>` 假 token，畫面會標示「模擬」。
 */
import type { PublicConfig, User } from "../api";
import { isApiError, post, setToken } from "../api";

export type LiffSession =
  | { status: "ok"; user: User; dev: boolean }
  | { status: "needs_binding"; idToken: string; dev: boolean };

async function loginWithToken(idToken: string): Promise<LiffSession> {
  const result = await post<{ status: string; session_token?: string; user?: User; dev?: boolean }>(
    "/api/auth/liff",
    { id_token: idToken },
  );
  if (result.status === "ok" && result.session_token && result.user) {
    setToken(result.session_token);
    return { status: "ok", user: result.user, dev: Boolean(result.dev) };
  }
  if (result.status === "needs_binding") {
    return { status: "needs_binding", idToken, dev: Boolean(result.dev) };
  }
  throw loginError("login_response", "登入服務回應異常，請稍後重試");
}

/** 真實 LINE：初始化 LIFF SDK、必要時導向 LINE Login，再以 ID token 登入後端。 */
export async function loginWithLiff(config: PublicConfig): Promise<LiffSession> {
  const liff = (await import("@line/liff")).default;
  try { await liff.init({ liffId: config.liff_id }); }
  catch { throw loginError("liff_init", "LINE 頁面初始化失敗，請確認網路，再從官方帳號重新開啟"); }
  if (!liff.isLoggedIn()) {
    liff.login({ redirectUri: window.location.href });
    return new Promise(() => undefined); // 頁面即將導向 LINE Login
  }
  const idToken = liff.getIDToken();
  if (!idToken) throw loginError("missing_line_token", "無法取得 LINE 登入狀態，請關閉頁面，再從官方帳號重新開啟");
  try { return await loginWithToken(idToken); }
  catch (e) {
    if (isApiError(e) && e.code === "invalid_token") {
      throw loginError("invalid_token", "LINE 登入驗證未通過，請按「重新進行 LINE 登入」，或關閉頁面後從官方帳號重新開啟", e.status);
    }
    throw e;
  }
}

/** 模擬模式：以指定 LINE userId 登入。 */
export async function loginDev(lineUserId: string): Promise<LiffSession> {
  return loginWithToken(`dev:${lineUserId}`);
}

export async function bindWithCode(idToken: string, code: string): Promise<User> {
  const result = await post<{ status: string; session_token: string; user: User }>("/api/auth/liff/bind", {
    id_token: idToken,
    binding_code: code,
  });
  setToken(result.session_token);
  return result.user;
}

/** 是否在 LINE 內建瀏覽器（LIFF）中；用來決定要不要提供「用外部瀏覽器開啟」替代入口。 */
export function isInLineApp(): boolean {
  return /Line\//i.test(navigator.userAgent);
}

function loginError(code: string, message: string, status = 0) {
  return { code, message, status, retryable: true };
}

/** Explicit recovery only: never treat SDK state as an authenticated app session. */
export async function reopenLiff(config: PublicConfig): Promise<void> {
  const liff = (await import("@line/liff")).default;
  try { await liff.init({ liffId: config.liff_id }); }
  catch { throw loginError("liff_init", "LINE 頁面初始化失敗，請確認網路，再從官方帳號重新開啟"); }
  if (liff.isInClient()) {
    window.location.replace(`https://liff.line.me/${encodeURIComponent(config.liff_id)}`);
    return;
  }
  if (liff.isLoggedIn()) liff.logout();
  liff.login({ redirectUri: window.location.origin + "/liff" });
}
