import { transferableAbortController } from "node:util";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router-dom";
import { AnswerCard } from "../src/liff/components";
import { AskPage } from "../src/liff/pages/AskPage";
import { AnswerPage } from "../src/liff/pages/AnswerPage";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  api: vi.fn(),
  user: { id: "caregiver-1", role: "caregiver", org: { id: "org-1" } },
}));

vi.mock("../src/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api")>();
  return {
    ...actual,
    post: mocks.post,
    api: mocks.api,
    newRequestId: () => "request-id-123",
    errorMessage: () => "測試錯誤",
  };
});

vi.mock("../src/liff/LiffApp", () => ({
  useLiff: () => ({
    config: { wake_words: ["小照"] },
    user: mocks.user,
  }),
}));

vi.mock("../src/liff/VoiceQuestion", () => ({
  VoiceQuestion: ({ onQuestion }: { onQuestion: (text: string, transcriptId?: string) => void }) => (
    <button onClick={() => onQuestion("語音測試問題")}>模擬語音送出</button>
  ),
}));

vi.mock("../src/quality/FeedbackCollector", () => ({
  FeedbackCollector: () => null,
}));

const answer = {
  id: "qa-1",
  conversation_id: "thread-1",
  created_at: "2026-11-08T00:00:00Z",
  outcome: "clarify",
  label: "AI 初步參考",
  question_masked: "測試問題",
  answer_text: "請再說明",
  claims: [],
  citations: [],
  escalation_reason: null,
  escalation_reason_text: null,
  case: null,
  manual_case: null,
  case_error: null,
  feedback_wrong: false,
  tts: null,
  modes: { llm: "mock" },
  qa_policy_version: "test",
  wake_word: false,
};

function LocationState() {
  const location = useLocation();
  return <output data-testid="location-state">{JSON.stringify(location.state)}</output>;
}

function mountAsk(initialEntry: string | { pathname: string; state?: unknown }) {
  const router = createMemoryRouter([
    { path: "/liff/ask", element: <AskPage /> },
    { path: "/liff/answers/:id", element: <LocationState /> },
  ], { initialEntries: [initialEntry] });
  render(<RouterProvider router={router} />);
  return router;
}

async function submitTextQuestion() {
  fireEvent.click(screen.getByRole("button", { name: /文字/ }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "照護規範問題" } });
  fireEvent.click(screen.getByRole("button", { name: "送出問題" }));
  await screen.findByTestId("location-state");
}

beforeEach(() => {
  const controller = transferableAbortController();
  vi.stubGlobal("AbortController", controller.constructor);
  vi.stubGlobal("AbortSignal", controller.signal.constructor);
  mocks.post.mockReset().mockResolvedValue(answer);
  mocks.api.mockReset();
  mocks.user.id = "caregiver-1";
  mocks.user.role = "caregiver";
  mocks.user.org = { id: "org-1" };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LIFF conversation Context", () => {
  it("starts a new thread without inheriting an earlier conversation", async () => {
    mountAsk("/liff/ask");

    await submitTextQuestion();

    const [path, body] = mocks.post.mock.calls[0];
    expect(path).toBe("/api/qa/ask");
    expect(body).not.toHaveProperty("conversation_id");
    expect(body).not.toHaveProperty("case_id");
    expect(body).not.toHaveProperty("case_context");
    expect(JSON.parse(screen.getByTestId("location-state").textContent ?? "{}").answer.conversation_id).toBe("thread-1");
  });

  it("does not forward case Context from untrusted navigation state", async () => {
    mountAsk({ pathname: "/liff/ask", state: {
      case_id: "case-placeholder",
      case_context: "untrusted-placeholder",
    } });

    await submitTextQuestion();

    const [, body] = mocks.post.mock.calls[0];
    expect(body).not.toHaveProperty("case_id");
    expect(body).not.toHaveProperty("case_context");
  });

  it("sends the existing thread only when opened with explicit continuation state", async () => {
    mountAsk({ pathname: "/liff/ask", state: { conversation_id: "thread-previous" } });

    await submitTextQuestion();

    expect(mocks.post).toHaveBeenCalledWith("/api/qa/ask", expect.objectContaining({
      conversation_id: "thread-previous",
      question: "照護規範問題",
    }));
  });

  it("preserves the thread for voice and confirmed-transcript questions", async () => {
    mountAsk({ pathname: "/liff/ask", state: { conversation_id: "thread-voice" } });
    fireEvent.click(screen.getByRole("button", { name: "模擬語音送出" }));
    await screen.findByTestId("location-state");
    expect(mocks.post).toHaveBeenCalledWith("/api/qa/ask", expect.objectContaining({
      source: "voice",
      conversation_id: "thread-voice",
    }));

    cleanup();
    mocks.post.mockClear().mockResolvedValue(answer);
    mountAsk({ pathname: "/liff/ask", state: {
      conversation_id: "thread-transcript",
      transcript_id: "transcript-1",
      question: "已確認逐字稿問題",
    } });
    fireEvent.click(screen.getByRole("button", { name: "送出問題" }));
    await screen.findByTestId("location-state");
    expect(mocks.post).toHaveBeenCalledWith("/api/qa/ask", expect.objectContaining({
      source: "transcript",
      transcript_id: "transcript-1",
      conversation_id: "thread-transcript",
    }));
  });

  it("drops a prior thread when the signed-in user changes on the same route", async () => {
    mountAsk({ pathname: "/liff/ask", state: { conversation_id: "thread-old-user" } });
    mocks.user.id = "caregiver-2";
    await submitTextQuestion();

    expect(mocks.post).toHaveBeenCalledWith("/api/qa/ask", expect.not.objectContaining({
      conversation_id: "thread-old-user",
    }));
  });

  it("passes the thread only through the explicit Continue asking link", async () => {
    const router = createMemoryRouter([
      { path: "/answer", element: <AnswerCard answer={answer} onChange={vi.fn()} conversationId={answer.conversation_id} /> },
      { path: "/liff/ask", element: <LocationState /> },
    ], { initialEntries: ["/answer"] });
    render(<RouterProvider router={router} />);

    fireEvent.click(screen.getByRole("link", { name: "💬 繼續提問" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/liff/ask"));
    expect(router.state.location.state).toEqual({ conversation_id: "thread-1" });
  });

  it("does not offer another user's thread to a supervisor viewing an answer", async () => {
    mocks.user.role = "supervisor";
    mocks.api.mockResolvedValue(answer);
    const router = createMemoryRouter([
      { path: "/liff/answers/:id", element: <AnswerPage /> },
      { path: "/liff/ask", element: <LocationState /> },
    ], { initialEntries: ["/liff/answers/qa-1"] });
    render(<RouterProvider router={router} />);

    fireEvent.click(await screen.findByRole("link", { name: "💬 繼續提問" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/liff/ask"));
    expect(router.state.location.state).toBeNull();
  });
});
