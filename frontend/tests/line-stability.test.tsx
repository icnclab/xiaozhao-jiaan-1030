import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, getToken, SESSION_EXPIRED_EVENT, setToken } from "../src/api";
import { installChunkRecovery } from "../src/recovery";

describe("LINE session and chunk recovery", () => {
  beforeEach(() => { sessionStorage.clear(); vi.restoreAllMocks(); });
  afterEach(() => vi.unstubAllGlobals());

  it("clears an expired app session and asks the LIFF shell to reverify", async () => {
    setToken("expired-session");
    const expired = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, expired, { once: true });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      error: { code: "session_expired", message: "登入已失效" },
    }), { status: 401 })));
    await expect(api("/api/qa/ask", { method: "POST", body: "{}" })).rejects.toMatchObject({ status: 401 });
    expect(getToken()).toBeNull();
    expect(expired).toHaveBeenCalledOnce();
  });

  it("does not turn a forbidden role into a login loop", async () => {
    setToken("valid-session");
    const expired = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, expired, { once: true });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      error: { code: "forbidden", message: "權限不足" },
    }), { status: 403 })));
    await expect(api("/api/qa/supervisor-ask", { method: "POST", body: "{}" })).rejects.toMatchObject({ status: 403 });
    expect(getToken()).toBe("valid-session");
    expect(expired).not.toHaveBeenCalled();
  });

  it("reloads only once for the same stale chunk URL", () => {
    const listeners = new Map<string, EventListener>();
    const storage = new Map<string, string>();
    const reload = vi.fn();
    const fakeWindow = {
      location: { href: "https://example.test/liff/ask", reload },
      sessionStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => storage.set(key, value),
        removeItem: (key: string) => storage.delete(key),
      },
      addEventListener: (name: string, listener: EventListener) => listeners.set(name, listener),
      removeEventListener: (name: string) => listeners.delete(name),
    } as unknown as Window;
    const dispose = installChunkRecovery(fakeWindow);
    listeners.get("vite:preloadError")?.(new Event("vite:preloadError", { cancelable: true }));
    listeners.get("vite:preloadError")?.(new Event("vite:preloadError", { cancelable: true }));
    expect(reload).toHaveBeenCalledOnce();
    dispose();
  });
});
