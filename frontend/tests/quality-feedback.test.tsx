import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { api, post, type Answer } from "../src/api";
import { FeedbackCollector } from "../src/quality/FeedbackCollector";
import { OriginalCorrection, TraceSummary, ReviewHistory, OriginalSources, reasonLabel } from "../src/quality/FeedbackReviewContext";
import { ReviewEvidenceFields } from "../src/quality/ReviewEvidenceFields";
import { FeedbackFields } from "../src/quality/FeedbackFields";
import { AdminQualityFeedbackPage } from "../src/quality/AdminQualityFeedbackPage";

const auth = vi.hoisted(() => ({ role: "supervisor" }));
vi.mock("../src/admin/AdminApp", () => ({ useAdmin: () => ({ user: { role: auth.role } }) }));

vi.mock("../src/api", async importOriginal => ({ ...await importOriginal<typeof import('../src/api')>(),
  api: vi.fn(), post: vi.fn(), getToken: () => "fixture", formatTime: (s: string) => s,
  newRequestId: () => "fixture-request" }));
afterEach(cleanup);
beforeEach(() => { auth.role = "supervisor"; vi.mocked(api).mockReset(); vi.mocked(post).mockReset(); });
const answer = (outcome = "answered") => ({ id: "qa1", outcome, feedback_wrong: false } as Answer);
const correction = { error_type: "incomplete_answer", expected_behavior: "answer", correct_answer: "原提交答案",
  correct_source_document: "文件", correct_source_page_or_section: "第1頁", evidence_summary: "依據", notes: "" };
const row = { id: "fb1", qa_id: "qa1", status: "pending_review", revision: 0,
  submission: correction, reviewed_correction: null, created_at: "2026-10-11", review_history: [],
  qa_snapshot: { question: "原問題", ai_answer: "原回答", sources: [{ document_title: "文件", locator: "第1頁", text: "來源原文", source_url: "/api/sources/chunks/1" }], runtime: { risk_gate_result: [] } } };

describe("structured feedback collector", () => {
  it.each([
    ["repetitive_answer", "direct_answer"], ["incomplete_answer", "concise_answer"],
    ["verbose_answer", "concise_answer"], ["duplicate_citation", "direct_answer"],
  ])("submits structured option %s / %s without remapping", async (errorType, behavior) => {
    vi.mocked(api).mockResolvedValue(null);
    vi.mocked(post).mockResolvedValue({ id: "fb1", status: "pending_review" });
    render(<FeedbackCollector answer={answer()} onChange={vi.fn()} />);
    fireEvent.click(screen.getByText("❌ 回答有誤"));
    await screen.findByText("提交品質回饋");
    for (const label of ["回答內容重複", "回答不完整", "回答過度冗長", "引用重複", "應直接回答", "應簡潔回答"]) {
      expect(screen.getByRole("option", { name: label })).toBeTruthy();
    }
    fireEvent.change(screen.getByLabelText("錯誤類型"), { target: { value: errorType } });
    fireEvent.change(screen.getByLabelText("預期行為"), { target: { value: behavior } });
    fireEvent.click(screen.getByText("提交品質回饋"));
    await screen.findByText("已提交品質回饋（待審核）");
    expect(post).toHaveBeenCalledWith("/api/quality/qa/qa1/feedback", expect.objectContaining({ error_type: errorType, expected_behavior: behavior }));
  });
  it.each(["answered", "escalated", "clarify"])("allows feedback for %s and submits correction only", async outcome => {
    vi.mocked(api).mockResolvedValue(null);
    vi.mocked(post).mockResolvedValue({ id: "fb1", status: "pending_review" });
    const change = vi.fn();
    render(<FeedbackCollector answer={answer(outcome)} onChange={change} />);
    fireEvent.click(screen.getByText("❌ 回答有誤"));
    await screen.findByText("提交品質回饋");
    fireEvent.change(screen.getByLabelText("錯誤類型"), { target: { value: "false_refusal" } });
    fireEvent.change(screen.getByLabelText("預期行為"), { target: { value: "clarify" } });
    fireEvent.change(screen.getByLabelText("建議正確答案"), { target: { value: "先追問" } });
    fireEvent.click(screen.getByText("提交品質回饋"));
    await screen.findByText("已提交品質回饋（待審核）");
    expect(post).toHaveBeenCalledWith("/api/quality/qa/qa1/feedback", expect.objectContaining({
      error_type: "false_refusal", expected_behavior: "clarify", correct_answer: "先追問" }));
    expect(Object.keys(vi.mocked(post).mock.calls[0][1] as object)).not.toContain("qa_snapshot");
    expect(change).toHaveBeenCalledOnce();
  });
  it("shows retry error and never marks failed submission as saved", async () => {
    vi.mocked(api).mockResolvedValue(null);
    vi.mocked(post).mockRejectedValue({ message: "暫時失敗" });
    const change = vi.fn();
    render(<FeedbackCollector answer={answer()} onChange={change} />);
    fireEvent.click(screen.getByText("❌ 回答有誤"));
    fireEvent.click(await screen.findByText("提交品質回饋"));
    await screen.findByRole("alert");
    expect(change).not.toHaveBeenCalled();
    expect(screen.queryByText("已提交品質回饋（待審核）")).toBeNull();
  });
  it("recognizes existing own feedback without duplicate submit", async () => {
    vi.mocked(api).mockResolvedValue({ id: "fb1", status: "verified" });
    render(<FeedbackCollector answer={answer()} onChange={vi.fn()} />);
    fireEvent.click(screen.getByText("❌ 回答有誤"));
    await screen.findByText("已提交品質回饋（已驗證）");
    expect(post).not.toHaveBeenCalled();
  });
});

describe("review workflow", () => {
  it("displays original evidence, edits reviewed correction, and requires evidence confirmation", async () => {
    auth.role = "admin";
    vi.mocked(api).mockImplementation(async path => path.endsWith("/fb1") ? row : [row]);
    vi.mocked(post).mockResolvedValue({ ...row, status: "verified" });
    render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
    fireEvent.click(await screen.findByText("檢視與審核"));
    await screen.findByText("原回答引用來源（1 筆）");
    fireEvent.click(screen.getByText("查看原回答引用"));
    await screen.findByText("來源原文");
    const button = screen.getByText("驗證") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("建議正確答案"), { target: { value: "審核修正版" } });
    fireEvent.click(screen.getByLabelText("我已核對正確答案／行為及原文依據"));
    fireEvent.click(button);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/quality/feedback/fb1/review", expect.objectContaining({
      correct_answer: "審核修正版", expected_revision: 0, status: "verified", evidence_checked: true })));
    expect(row.submission.correct_answer).toBe("原提交答案");
  });
  it("requeries current status", async () => {
    vi.mocked(api).mockResolvedValue([]);
    render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/quality/feedback?status=pending_review"));
    fireEvent.change(screen.getByLabelText("狀態"), { target: { value: "verified" } });
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/quality/feedback?status=verified"));
    fireEvent.click(screen.getByText("重新整理"));
    await waitFor(() => expect(vi.mocked(api).mock.calls.filter(([p]) => p.endsWith("status=verified")).length).toBe(2));
  });
});


describe("review form scrolling", () => {
  const scrollIntoView = vi.fn();
  let original: PropertyDescriptor | undefined;
  beforeEach(() => {
    original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollIntoView");
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scrollIntoView });
    scrollIntoView.mockClear();
  });
  afterEach(() => {
    if (original) Object.defineProperty(HTMLElement.prototype, "scrollIntoView", original);
    else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
  });
  const second = { ...row, id: "fb2", qa_id: "qa2", submission: { ...correction, correct_answer: "Second correction" },
    qa_snapshot: { ...row.qa_snapshot, question: "Second question" } };
  const setup = () => {
    vi.mocked(api).mockImplementation(async path => path.endsWith("/fb1") ? row : path.endsWith("/fb2") ? second : [row, second]);
    render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
  };
  it("opens the selected item and smoothly scrolls to its review form", async () => {
    setup();
    const buttons = await screen.findAllByRole("button", { name: /\u6aa2\u8996\u8207\u5be9\u6838/ });
    fireEvent.click(buttons[0]);
    const form = await screen.findByRole("region", { name: "\u539f\u554f\u7b54\u8207\u4fee\u6b63" });
    expect(form.getAttribute("data-feedback-id")).toBe("fb1");
    expect(screen.getByLabelText("\u5efa\u8b70\u6b63\u78ba\u7b54\u6848")).toHaveProperty("value", correction.correct_answer);
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    expect(scrollIntoView.mock.contexts[0]).toBe(form);
    expect((form as HTMLElement).style.scrollMarginTop).toBe("calc(var(--admin-fixed-header-height, 0px) + 16px)");
    fireEvent.change(screen.getByLabelText("\u5efa\u8b70\u6b63\u78ba\u7b54\u6848"), { target: { value: "Edited" } });
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });
  it("scrolls to the newly expanded form when switching feedback", async () => {
    setup();
    const buttons = await screen.findAllByRole("button", { name: /\u6aa2\u8996\u8207\u5be9\u6838/ });
    fireEvent.click(buttons[0]);
    const firstForm = await screen.findByRole("region", { name: "\u539f\u554f\u7b54\u8207\u4fee\u6b63" });
    await waitFor(() => expect((buttons[1] as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(buttons[1]);
    await waitFor(() => expect(screen.getByRole("region", { name: "\u539f\u554f\u7b54\u8207\u4fee\u6b63" }).getAttribute("data-feedback-id")).toBe("fb2"));
    const secondForm = screen.getByRole("region", { name: "\u539f\u554f\u7b54\u8207\u4fee\u6b63" });
    expect(secondForm).not.toBe(firstForm);
    expect(screen.getByLabelText("\u5efa\u8b70\u6b63\u78ba\u7b54\u6848")).toHaveProperty("value", "Second correction");
    expect(scrollIntoView).toHaveBeenCalledTimes(2);
    expect(scrollIntoView.mock.contexts).toEqual([firstForm, secondForm]);
  });
});


it("keeps both source inputs full width within the responsive form", () => {
  const change = vi.fn();
  const { container } = render(<FeedbackFields value={correction} onChange={change} />);
  const inputs = container.querySelectorAll<HTMLInputElement>('input[type="text"]');
  expect(inputs).toHaveLength(2);
  expect(inputs[0].value).toBe(correction.correct_source_document);
  expect(inputs[1].value).toBe(correction.correct_source_page_or_section);
  for (const input of inputs) {
    expect(input.style.width).toBe("100%");
    expect(input.style.maxWidth).toBe("100%");
    expect(input.style.minWidth).toBe("0px");
    expect(input.style.display).toBe("block");
  }
  expect(container.querySelector("fieldset")?.style.minWidth).toBe("0px");
  fireEvent.change(inputs[1], { target: { value: "Section 2" } });
  expect(change).toHaveBeenCalledWith({ ...correction, correct_source_page_or_section: "Section 2" });
});


describe("human readable review context", () => {
  it("shows Chinese original correction and hides JSON until clicked", async () => {
    const submission = { ...correction, error_type: "risk_false_negative", expected_behavior: "risk_block" };
    render(<OriginalCorrection submission={submission} />);
    expect(screen.getByText("使用者原始回饋")).toBeTruthy();
    for (const label of ["錯誤類型", "預期行為", "漏掉風險", "風險攔截"]) expect(screen.queryByText(label)).toBeNull();
    const originalDetails = screen.getByText("查看完整原始回饋").parentElement as HTMLDetailsElement;
    expect(originalDetails.open).toBe(false);
    for (const label of ["建議正確答案", "正確來源文件", "頁碼／章節", "依據摘要", "補充說明", "查看原始 JSON"]) expect(screen.queryByText(label)).toBeNull();
    fireEvent.click(screen.getByText("查看完整原始回饋"));
    await screen.findByText("建議正確答案");
    for (const label of ["錯誤類型", "預期行為", "漏掉風險", "風險攔截", "正確來源文件", "頁碼／章節", "依據摘要", "補充說明"]) expect(screen.getByText(label)).toBeTruthy();
    expect(document.querySelector("pre")).toBeNull();
    expect(submission.correct_answer).toBe(correction.correct_answer);
  });
  it("shows supervisor summary without technical parameters or trace", () => {
    const runtime = { retrieval_candidates: [{ chunk_id: "secret-chunk" }], risk_gate_result: { codes: ["risk_medication"] }, escalation_result: { outcome: "escalate", reason: "no_evidence" }, top_k: 5, candidate_k: 50, rag_version: "rag-v1", qa_policy_version: "policy-v1" };
    render(<TraceSummary role="supervisor" snapshot={{ runtime, sources: [{}] }} />);
    expect(screen.getByText("找不到足夠資料")).toBeTruthy();
    expect(screen.getByText("命中：用藥安全")).toBeTruthy();
    expect(screen.getByText("轉人工")).toBeTruthy(); expect(screen.queryByText("是否轉人工")).toBeNull();
    for (const label of ["top_k", "candidate_k", "RAG version", "qa_policy_version", "檢索候選數量", "採用依據數量（原回答引用）", "查看技術診斷資訊"]) expect(screen.queryByText(label)).toBeNull();
    expect(document.querySelector("pre")).toBeNull();
  });
  it("lets admin expand the full technical diagnosis", async () => {
    const runtime = { normalized_query: "normalized", expanded_query: "expanded", retrieval_candidates: [{ chunk_id: "chunk1", vector_score: .7 }, { chunk_id: "chunk2" }], risk_gate_result: { codes: [] }, escalation_result: { outcome: "answered", reason: null }, top_k: 5, candidate_k: 50, rag_version: "rag-v1", qa_policy_version: "policy-v1", evidence_gate_result: { passed: true } };
    render(<TraceSummary role="admin" snapshot={{ runtime, sources: [{}] }} />);
    expect(document.querySelector("pre")).toBeNull();
    expect(screen.queryByText("top_k")).toBeNull();
  });
  it("translates known reason codes and preserves unknown codes", () => {
    expect(reasonLabel("no_evidence")).toBe("找不到足夠資料");
    expect(reasonLabel("risk_medication")).toBe("用藥安全");
    expect(reasonLabel("risk_false_negative")).toBe("漏掉風險");
    expect(reasonLabel("new_code")).toBe("需要確認");
  });
  it("does not invent missing trace values", () => {
    render(<TraceSummary snapshot={{ runtime: {}, sources: [] }} />);
    expect(screen.getByText("風險判斷").closest("dt")?.parentElement?.querySelector("dd")?.textContent).toBe("未記錄");
  });
  it("shows empty history as text and existing history as a table", () => {
    const { rerender } = render(<ReviewHistory history={[]} />);
    expect(screen.getByText("尚無審核紀錄")).toBeTruthy(); expect(document.querySelector("pre")).toBeNull();
    rerender(<ReviewHistory history={[{ created_at: "2026-10-11", reviewer_id: "reviewer1", decision: "verified", correction: { reviewer_notes: "Checked source" } }]} />);
    expect(screen.queryByText("尚無審核紀錄")).toBeNull(); expect(screen.getByRole("table")).toBeTruthy();
    for (const value of ["已驗證", "reviewer1", "Checked source", "2026-10-11"]) expect(screen.getByText(value)).toBeTruthy();
  });
  it("preserves the rejection API payload", async () => {
    vi.mocked(api).mockImplementation(async path => path.endsWith("/fb1") ? row : [row]);
    vi.mocked(post).mockResolvedValue({ ...row, status: "rejected" });
    render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
    fireEvent.click(await screen.findByText("檢視與審核"));
    fireEvent.click(await screen.findByText("駁回"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/quality/feedback/fb1/review", expect.objectContaining({ ...correction, status: "rejected", expected_revision: 0 })));
  });
});

it("uses the authenticated page role for technical diagnosis access", async () => {
  vi.mocked(api).mockImplementation(async path => path.endsWith("/fb1") ? row : [row]);
  const { rerender } = render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
  fireEvent.click(await screen.findByText("檢視與審核"));
  await screen.findByText("系統處理摘要");
  expect(screen.queryByText("查看技術診斷資訊")).toBeNull();
  expect(await screen.findByText("尚無審核紀錄")).toBeTruthy();
  auth.role = "admin";
  rerender(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
  fireEvent.click(await screen.findByText("檢視與審核"));
  expect(screen.queryByText("查看技術診斷資訊")).toBeNull();
  expect(await screen.findByText("尚無審核紀錄")).toBeTruthy();
});


describe("legacy feedback loading", () => {
  it("shows loading and empty success, and prevents duplicate loads", async () => {
    let resolve!: (rows: unknown[]) => void;
    const pending = new Promise<unknown[]>(done => { resolve = done; });
    vi.mocked(api).mockImplementation(async path => path === "/api/admin/feedback" ? pending : []);
    render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
    expect((screen.getByText("舊版單純回饋（不納入 已驗證資料集）").parentElement as HTMLDetailsElement).open).toBe(false);
    fireEvent.click(screen.getByText("舊版單純回饋（不納入 已驗證資料集）"));
    fireEvent.click(screen.getByText("載入既有回饋"));
    expect((screen.getByText("載入中…") as HTMLButtonElement).disabled).toBe(true);
    resolve([]);
    await screen.findByText("無舊版回饋");
    expect(screen.queryByText("已載入，目前沒有舊版回饋")).toBeNull();
    const button = screen.getByText("無舊版回饋") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(vi.mocked(api).mock.calls.filter(([path]) => path === "/api/admin/feedback")).toHaveLength(1);
  });
  it("lists legacy feedback without replacing the auto-filled review correction", async () => {
    vi.mocked(api).mockImplementation(async path => path === "/api/admin/feedback" ? [{ id: "old1", qa_item_id: "oldqa", question_masked: "Legacy question", kind: "wrong", status: "new" }] : path.endsWith("/fb1") ? row : [row]);
    render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
    fireEvent.click(await screen.findByText("檢視與審核"));
    const field = await screen.findByLabelText("建議正確答案") as HTMLTextAreaElement;
    expect(field.value).toBe(correction.correct_answer);
    fireEvent.change(field, { target: { value: "Review edit" } });
    expect((screen.getByText("舊版單純回饋（不納入 已驗證資料集）").parentElement as HTMLDetailsElement).open).toBe(false);
    fireEvent.click(screen.getByText("舊版單純回饋（不納入 已驗證資料集）"));
    fireEvent.click(screen.getByText("載入既有回饋"));
    await screen.findByText("已載入 1 筆舊版回饋");
    expect(screen.getByText(/Legacy question/)).toBeTruthy();
    expect(field.value).toBe("Review edit");
    expect(screen.getByRole("link", { name: "查看" }).getAttribute("href")).toBe("/liff/answers/oldqa");
  });
  it("reports load failure and permits retry", async () => {
    vi.mocked(api).mockImplementation(async path => { if (path === "/api/admin/feedback") throw { message: "Legacy load failed" }; return []; });
    render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
    expect((screen.getByText("舊版單純回饋（不納入 已驗證資料集）").parentElement as HTMLDetailsElement).open).toBe(false);
    fireEvent.click(screen.getByText("舊版單純回饋（不納入 已驗證資料集）"));
    fireEvent.click(screen.getByText("載入既有回饋"));
    await screen.findByText("系統目前無法完成回答，請稍後再試或送交督導確認");
    expect((screen.getByText("載入既有回饋") as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText("已載入")).toBeNull();
  });
});


describe("original answer citations", () => {
  it("starts collapsed with the correct count and reveals complete read-only sources", async () => {
    render(<OriginalSources sources={row.qa_snapshot.sources} />);
    const section = screen.getByRole("region", { name: "原回答引用來源（1 筆）" });
    const details = screen.getByText("查看原回答引用").parentElement as HTMLDetailsElement;
    expect(details.open).toBe(false); expect(screen.queryByText("來源原文")).toBeNull();
    fireEvent.click(screen.getByText("查看原回答引用"));
    await screen.findByText("來源原文");
    expect(screen.getByText("文件／第1頁")).toBeTruthy();
    expect(screen.getByRole("link", { name: "原引用入口" }).getAttribute("href")).toBe("/api/sources/chunks/1");
    expect(section.querySelector("input, textarea, select")).toBeNull();
  });
  it.each(["supervisor", "admin"])("separates citations from review controls for %s", async role => {
    auth.role = role;
    vi.mocked(api).mockImplementation(async path => path.endsWith("/fb1") ? row : [row]);
    render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
    fireEvent.click(await screen.findByText("檢視與審核"));
    const section = await screen.findByRole("region", { name: "原回答引用來源（1 筆）" });
    const field = screen.getByLabelText("建議正確答案");
    expect(section.contains(field)).toBe(false);
    expect(field.closest("fieldset")?.contains(section)).toBe(false);
    expect(section.classList.contains("card")).toBe(true);
    fireEvent.click(screen.getByText("查看原回答引用"));
    await screen.findByText("來源原文");
    expect(Boolean(screen.queryByText("查看技術診斷資訊"))).toBe(false);
  });
  it("shows the zero citation count without inventing sources", async () => {
    render(<OriginalSources sources={[]} />);
    expect(screen.getByText("原回答引用來源（0 筆）")).toBeTruthy();
    fireEvent.click(screen.getByText("查看原回答引用"));
    await screen.findByText("原回答沒有引用來源");
  });
});


describe("gold evidence review", () => {
  it.each([
    ["system_safety_policy", ["政策識別／名稱", "政策版本"]],
    ["institution_policy", ["機構識別資訊", "機構規範識別／版本"]],
    ["expert_review", ["專業覆核紀錄"]],
  ])("shows required fields for %s and hides PDF fields", (basis, labels) => {
    const value = { ...correction, evidence_basis_type: basis };
    render(<><ReviewEvidenceFields value={value} onChange={vi.fn()} disabled={false} /><FeedbackFields value={value} onChange={vi.fn()} reviewMode /></>);
    for (const label of labels) expect(screen.getByLabelText(label)).toBeTruthy();
    expect(screen.queryByLabelText("頁碼／章節")).toBeNull();
    expect(screen.queryByLabelText("正確來源文件")).toBeNull();
    expect(screen.getByLabelText("依據摘要")).toBeTruthy();
  });
  it("supports explicit evidence classification and manual completeness checks", () => {
    const change = vi.fn();render(<ReviewEvidenceFields value={correction} onChange={change} disabled={false} />);
    expect((screen.getByLabelText("依據類型") as HTMLSelectElement).value).toBe("");
    fireEvent.change(screen.getByLabelText("依據類型"), { target: { value: "pending_evidence" } });
    expect(change).toHaveBeenCalledWith({ ...correction, evidence_basis_type: "pending_evidence" });
    fireEvent.click(screen.getByLabelText("已確認正確答案完整且不是編輯指令"));
    expect(change).toHaveBeenCalledWith({ ...correction, complete_answer_confirmed: true });
  });
  it("shows saved gold state without technical details and keeps both exports", async () => {
    const goldRow = { ...row, gold_readiness: "needs_review" };
    vi.mocked(api).mockImplementation(async path => path.endsWith("/fb1") ? goldRow : [goldRow]);
    render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
    fireEvent.click(await screen.findByText("檢視與審核"));
    await screen.findByText(/標準案例資料狀態：需要管理員重新審核/);
    expect(screen.queryByText("匯出正式標準案例JSON")).toBeNull();
    expect(screen.getByText("匯出已驗證 JSON")).toBeTruthy();
    expect(screen.queryByText("answer_completeness_unconfirmed")).toBeNull();
  });
});


describe("role-aware gold management", () => {
  it("allows supervisor corrections without any protected gold payload", async () => {
    const detail = { ...row, reviewed_correction: { ...correction, evidence_basis_type: "system_safety_policy", policy_version: "v1", evidence_checked: true, complete_answer_confirmed: true } };
    vi.mocked(api).mockImplementation(async path => path.endsWith("/fb1") ? detail : [detail]);vi.mocked(post).mockResolvedValue(detail);
    render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
    fireEvent.click(await screen.findByText("檢視與審核"));await screen.findByLabelText("建議正確答案");
    for (const label of ["依據類型", "政策版本", "已確認正確答案完整且不是編輯指令", "尚待解決的資料品質問題", "我已核對正確答案／行為及原文依據"]) expect(screen.queryByLabelText(label)).toBeNull();
    expect(screen.getByLabelText("正確來源文件")).toBeTruthy();
    for (const text of ["標準案例資料管理", "匯出正式標準案例JSON", "查看技術診斷資訊"]) expect(screen.queryByText(text)).toBeNull();
    fireEvent.change(screen.getByLabelText("建議正確答案"), { target: { value: "Supervisor correction" } });fireEvent.click(screen.getByText("驗證"));
    await waitFor(() => expect(post).toHaveBeenCalled());const body = vi.mocked(post).mock.calls[0][1] as Record<string, unknown>;
    expect(body.correct_answer).toBe("Supervisor correction");
    for (const key of ["evidence_basis_type", "policy_version", "complete_answer_confirmed", "evidence_checked", "data_quality_checked", "data_quality_conflicts"]) expect(body).not.toHaveProperty(key);
  });
  it("offers admin stats, filters and priority queue", async () => {
    auth.role = "admin";
    vi.mocked(api).mockImplementation(async path => path === "/api/quality/gold/stats" ? { pending_review: 2, needs_review: 1, ready: 3, not_eligible: 4 } : [{ ...row, gold_readiness: "needs_review", gold_priority: "P0 安全" }]);
    render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);
    fireEvent.click(await screen.findByText("標準案例待重新審核：1"));
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/quality/feedback?status=verified&gold_readiness=needs_review"));
    fireEvent.click(screen.getByLabelText("只看標準案例待審核"));
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/quality/feedback?status=verified&gold_readiness=needs_review&gold_queue=true"));
    await screen.findByText("P0 安全");expect(screen.getByText("匯出正式標準案例JSON")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("標準案例資料狀態"), { target: { value: "ready" } });
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/quality/feedback?status=verified&gold_readiness=ready"));
  });
  it("shows admin metadata and no-conflict guidance", async () => {
    auth.role = "admin";vi.mocked(api).mockImplementation(async path => path.endsWith("/fb1") ? row : path.endsWith("/stats") ? {} : [row]);
    render(<MemoryRouter><AdminQualityFeedbackPage /></MemoryRouter>);fireEvent.click(await screen.findByText("檢視與審核"));
    await screen.findByLabelText("依據類型");expect(screen.getByPlaceholderText("若目前沒有待解決問題，請留白。")).toBeTruthy();
  });
});
