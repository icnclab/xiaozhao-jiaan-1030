// Real DOM execution test (vitest + jsdom) for the vanilla-JS field-test
// dashboard served at backend/app/static/fieldtest-dashboard.html. This file
// is outside the Vite/React build, so it has no existing harness; this test
// actually parses the real HTML, executes its real inline <script> against
// jsdom's document, and drives it the way a browser/user would (fill
// inputs, submit forms, click buttons) -- not a regex/static-text check.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const HTML_PATH = resolve(__dirname, "../../backend/app/static/fieldtest-dashboard.html");
const SOURCE = readFileSync(HTML_PATH, "utf-8");
const BODY_HTML = SOURCE.split("<body>")[1].split("<script>")[0];
const SCRIPT = SOURCE.split("<script>")[1].split("</script>")[0];

function mount() {
  document.body.innerHTML = BODY_HTML;
  // The script is a self-invoking IIFE that calls load() at the bottom;
  // executing it against the current jsdom `document`/`window` is the
  // same thing a real browser does when it parses this page.
  // eslint-disable-next-line no-new-func
  new Function(SCRIPT)();
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

const EMPTY_SUMMARY = {
  note: "test", total: 47, mapped: 0, with_records: 0,
  participants: Array.from({ length: 47 }, (_, i) => ({
    code: i < 40 ? `A${String(i + 1).padStart(2, "0")}` : `S${String(i - 39).padStart(2, "0")}`,
    role: i < 40 ? "照服員" : "居督", user_id: null, mapping_status: "待核對",
    audit_event_count: 0, qa_count: 0, case_count: 0, status: "待對應",
  })),
  event_records: 0, qa_records: 0, case_records: 0, error_records: 0,
};

beforeEach(() => {
  vi.stubGlobal("localStorage", { length: 0, key: () => null, getItem: () => null, setItem: () => undefined, removeItem: () => undefined });
  vi.stubGlobal("sessionStorage", { length: 0, key: () => null, getItem: () => null, setItem: () => undefined, removeItem: () => undefined });
  (globalThis as any).URL.createObjectURL = vi.fn(() => "blob:fake");
  (globalThis as any).URL.revokeObjectURL = vi.fn();
  HTMLAnchorElement.prototype.click = vi.fn();
});
afterEach(async () => {
  await flush(); // let any still-pending load()/download() promise from this test settle first
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

async function flush() {
  for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0));
}

describe("fieldtest dashboard: initial load never implies 47 people already participated", () => {
  it("shows mapped=0 / with_records=0 even though total slot count is 47", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(EMPTY_SUMMARY)));
    mount();
    await flush();
    expect(document.getElementById("total")!.textContent).toBe("47");
    expect(document.getElementById("mapped")!.textContent).toBe("0");
    expect(document.getElementById("records")!.textContent).toBe("0");
    // Every row must read 待核對/待對應, never a filled-in status.
    const rows = Array.from(document.querySelectorAll("#body tr"));
    expect(rows.length).toBe(47);
    expect(rows.every((r) => r.textContent!.includes("待核對") || r.textContent!.includes("待對應"))).toBe(true);
  });

  it("shows a clear 503 message (not blank/HTTP-only) when the table does not exist yet", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "場測資料表（fieldtest_participants）尚未建立，請管理員完成資料庫設定後再使用本功能" }, 503)));
    mount();
    await flush();
    const notice = document.getElementById("notice")!.textContent!;
    expect(notice).toContain("503");
    expect(notice).toContain("尚未建立");
    expect(document.getElementById("auth")!.classList.contains("hidden")).toBe(false);
  });
});

describe("fieldtest dashboard: mapping form", () => {
  it("accepts A01-A40 and S01-S07 patterns in the code input", () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(EMPTY_SUMMARY)));
    mount();
    const code = document.getElementById("mapCode") as HTMLInputElement;
    for (const valid of ["A01", "A40", "S01", "S07"]) {
      code.value = valid;
      expect(code.checkValidity()).toBe(true);
    }
    for (const invalid of ["T01", "A41x", "1A01"]) {
      code.value = invalid;
      expect(code.checkValidity()).toBe(false);
    }
  });

  it("on 200: looks up the username, saves, shows confirmation, and reloads the summary", async () => {
    // AdminUsersPage never shows a UUID -- the form must accept a username
    // and resolve it via GET /lookup before posting to /mappings.
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (String(url).includes("/lookup")) return jsonResponse({ user_id: "11111111-1111-1111-1111-111111111111", role: "caregiver" });
      if (init?.method === "POST") return jsonResponse({ ok: true, code: "A01", user_id: "11111111-1111-1111-1111-111111111111" });
      return jsonResponse(EMPTY_SUMMARY);
    }));
    mount();
    await flush();
    (document.getElementById("mapCode") as HTMLInputElement).value = "A01";
    (document.getElementById("mapUsername") as HTMLInputElement).value = "cg_happy_1";
    document.getElementById("mapForm")!.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    await flush();
    expect(document.getElementById("mapStatus")!.textContent).toContain("A01");
    expect(calls.some((c) => c.includes("/lookup?username=cg_happy_1"))).toBe(true);
    const postIndex = calls.findIndex((c) => c.startsWith("POST"));
    expect(postIndex).toBeGreaterThanOrEqual(0);
    // the body sent to /mappings must be the looked-up UUID, not the raw username
    expect(String((vi.mocked(fetch).mock.calls[postIndex]![1] as RequestInit).body)).toContain("11111111-1111-1111-1111-111111111111");
    expect(calls.slice(postIndex + 1).some((c) => c.includes("summary"))).toBe(true);
  });

  it("on lookup 404: shows a clear 'account not found' message, never a raw UUID prompt", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/lookup")) return jsonResponse({ detail: "此機構找不到帳號「no_such_user」" }, 404);
      return jsonResponse(EMPTY_SUMMARY);
    }));
    mount();
    await flush();
    (document.getElementById("mapCode") as HTMLInputElement).value = "A01";
    (document.getElementById("mapUsername") as HTMLInputElement).value = "no_such_user";
    document.getElementById("mapForm")!.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    await flush();
    const status = document.getElementById("mapStatus")!.textContent!;
    expect(status).toContain("404");
    expect(status).toContain("找不到帳號");
  });

  it("on 422: shows the backend's role/code-mismatch detail, not a generic message", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).includes("/lookup")) return jsonResponse({ user_id: "22222222-2222-2222-2222-222222222222", role: "supervisor" });
      if (init?.method === "POST") return jsonResponse({ detail: "帳號角色 supervisor 與編號類型不一致，未建立對應" }, 422);
      return jsonResponse(EMPTY_SUMMARY);
    }));
    mount();
    await flush();
    (document.getElementById("mapCode") as HTMLInputElement).value = "A01";
    (document.getElementById("mapUsername") as HTMLInputElement).value = "sup_happy_a";
    document.getElementById("mapForm")!.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    await flush();
    const status = document.getElementById("mapStatus")!.textContent!;
    expect(status).toContain("422");
    expect(status).toContain("與編號類型不一致");
  });

  it("on 403: shows a clear authorization message when even the lookup is refused", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) =>
      String(url).includes("/lookup") ? jsonResponse({ detail: "僅管理員可存取場測資料" }, 403) : jsonResponse(EMPTY_SUMMARY)));
    mount();
    await flush();
    (document.getElementById("mapCode") as HTMLInputElement).value = "A01";
    (document.getElementById("mapUsername") as HTMLInputElement).value = "cg_happy_1";
    document.getElementById("mapForm")!.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    await flush();
    expect(document.getElementById("mapStatus")!.textContent).toContain("僅管理員可存取場測資料");
  });

  it("on 503 (table missing): the lookup still succeeds, but saving the mapping shows the table-missing detail", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).includes("/lookup")) return jsonResponse({ user_id: "44444444-4444-4444-4444-444444444444", role: "caregiver" });
      if (init?.method === "POST") return jsonResponse({ detail: "場測資料表（fieldtest_participants）尚未建立，請管理員完成資料庫設定後再使用本功能" }, 503);
      return jsonResponse(EMPTY_SUMMARY);
    }));
    mount();
    await flush();
    (document.getElementById("mapCode") as HTMLInputElement).value = "A01";
    (document.getElementById("mapUsername") as HTMLInputElement).value = "cg_happy_1";
    document.getElementById("mapForm")!.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    await flush();
    const status = document.getElementById("mapStatus")!.textContent!;
    expect(status).toContain("503");
    expect(status).toContain("尚未建立");
  });
});

describe("fieldtest dashboard: Excel export", () => {
  it("on success: triggers a file download via an anchor click", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("export.xlsx")) {
        return new Response(new Blob(["fake-xlsx"]), { status: 200 });
      }
      return jsonResponse(EMPTY_SUMMARY);
    }));
    mount();
    await flush();
    document.getElementById("export")!.dispatchEvent(new Event("click", { bubbles: true }));
    await flush();
    expect((globalThis as any).URL.createObjectURL).toHaveBeenCalled();
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();
    expect(document.getElementById("notice")!.textContent).toBe("");
  });

  it("on failure: shows a clear error instead of a silent/blank failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("export.xlsx")) return jsonResponse({ detail: "匯出失敗：僅管理員可存取場測資料" }, 403);
      return jsonResponse(EMPTY_SUMMARY);
    }));
    mount();
    await flush();
    document.getElementById("export")!.dispatchEvent(new Event("click", { bubbles: true }));
    await flush();
    const notice = document.getElementById("notice")!.textContent!;
    expect(notice).toContain("403");
    expect(notice).toContain("匯出失敗");
    expect((globalThis as any).URL.createObjectURL).not.toHaveBeenCalled();
  });
});
