import { beforeAll, describe, expect, it, vi } from "vitest";

const base = process.env.MULTITURN_LIVE_API_URL;
const live = base ? describe : describe.skip;

live("frontend API client against isolated live API", () => {
  beforeAll(() => {
    const nativeFetch = globalThis.fetch;
    vi.stubGlobal("fetch", (input: string | URL | Request, init?: RequestInit) => {
      const target = typeof input === "string" && input.startsWith("/") ? `${base}${input}` : input;
      return nativeFetch(target, init);
    });
  });

  it("uses the production frontend api wrapper for a new question and explicit continuation", async () => {
    const cryptoModule = await import("node:crypto");
    const lineId = `U${cryptoModule.createHash("md5").update("demo:cg_pine_1").digest("hex")}`;
    const login = await fetch("/api/auth/liff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: `dev:${lineId}` }),
    });
    expect(login.status).toBe(200);
    const session = await login.json() as { session_token: string };

    const { post, setToken } = await import("../src/api");
    setToken(session.session_token);
    const first = await post<{ id: string; conversation_id: string }>("/api/qa/ask", {
      question: "夜間每多少位住民要配置一名照服員？",
      source: "text",
      transcript_id: null,
      client_request_id: crypto.randomUUID(),
    });
    expect(first.conversation_id).toBeTruthy();

    const continued = await post<{ id: string; conversation_id: string }>("/api/qa/ask", {
      question: "那夜間呢？",
      source: "text",
      transcript_id: null,
      conversation_id: first.conversation_id,
      client_request_id: crypto.randomUUID(),
    });
    expect(continued.conversation_id).toBe(first.conversation_id);
  });
});
