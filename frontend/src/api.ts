/**
 * API client：所有請求帶 Bearer session token；統一錯誤格式。
 * token 放 sessionStorage（分頁關閉即失效），不放 localStorage；音訊與逐字稿一律不落地瀏覽器儲存。
 */

import { publicMessage, SYSTEM_FAILURE } from './publicText';
export interface ApiError {
  code: string;
  message: string;
  retryable: boolean;
  status: number;
}

const TOKEN_KEY = "ltc_session";

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* 私密瀏覽等情境：僅記憶體 */
  }
}

export function newRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function parse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch {
    throw { code: "network", message: "網路連線失敗，請確認網路後重試", retryable: true, status: 0 } as ApiError;
  }
  const body = (await parse(response)) as { error?: Partial<ApiError> } | null;
  if (!response.ok) {
    const err = body?.error ?? {};
    throw {
      code: err.code ?? `http_${response.status}`,
      message: response.status >= 500 ? SYSTEM_FAILURE : publicMessage(err.message),
      retryable: err.retryable ?? response.status >= 500,
      status: response.status,
    } as ApiError;
  }
  return body as T;
}

export const post = <T,>(path: string, data: unknown) =>
  api<T>(path, { method: "POST", body: JSON.stringify(data) });

export function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "code" in value && "message" in value;
}

export function errorMessage(value: unknown): string {
  if (isApiError(value)) return publicMessage(value.message);
  return SYSTEM_FAILURE;
}

// ── 型別 ──────────────────────────────────────────────────────────────

export interface PublicConfig {
  line_mode: "mock" | "real";
  liff_id: string;
  dev_features: boolean;
  modes: Record<string, string>;
  limits: { question_max_sec: number; conversation_max_sec: number; max_upload_mb: number };
  consent_text: string;
  consent_text_version: string;
  qa_policy_version: string;
  bot_name: string;
  wake_words: string[];
}

export interface User {
  id: string;
  display_name: string;
  role: "caregiver" | "supervisor" | "director" | "admin";
  username: string;
  org: { id: string; name: string; facility_type: string } | null;
}

export interface Citation {
  id: string;
  chunk_id: string;
  version_id: string;
  document_title: string;
  doc_type: string;
  locator: string;
  version_label: string;
  effective_from: string | null;
  effective_to: string | null;
  version_status: string;
  source: string | null;
  source_url: string;
  external_url: string | null;
  excerpt: string;
}

export interface CaseBrief {
  id: string;
  number: string;
  status: string;
  status_label: string;
}

export interface Answer {
  id: string;
  conversation_id?: string;
  created_at: string;
  outcome: "answered" | "clarify" | "escalated" | "escalation_failed";
  label: string;
  question_masked: string;
  answer_text: string | null;
  claims: { text: string; citations: string[] }[];
  safety_notice?: string | null;
  citations: Citation[];
  escalation_reason: string | null;
  escalation_reason_text: string | null;
  case: CaseBrief | null;
  manual_case: CaseBrief | null;
  case_error: string | null;
  feedback_wrong: boolean;
  tts: { status: string; audio_url: string | null; error: string | null } | null;
  modes: Record<string, string>;
  qa_policy_version: string;
  wake_word: boolean;
}

export interface Segment {
  idx: number;
  start_ms: number;
  end_ms: number;
  speaker: string;
  text: string;
  uncertain: boolean;
  edited?: boolean;
  selected?: boolean;
  masked: boolean;
}

export interface Transcript {
  id: string;
  status: string;
  mode: "question" | "conversation";
  channel: string;
  audio_duration_ms: number | null;
  error_code: string | null;
  error_message: string | null;
  draft_expires_at: string | null;
  audio_deleted: boolean;
  roles: Record<string, string>;
  summary_masked: string | null;
  segments: Segment[];
  stt_provider: string | null;
  stt_ms: number | null;
}

export interface Category {
  id: string;
  name: string;
  description: string | null;
  templates: { id: string; text: string }[];
}

export interface CaseMessage {
  id: string;
  author_role: string;
  author_name: string;
  body: string;
  created_at: string;
}

export interface CaseDetail {
  id: string;
  number: string;
  status: string;
  status_label: string;
  source: string;
  source_label: string;
  category: { id: string; name: string } | null;
  summary_masked: string;
  reason: string;
  created_at: string;
  updated_at: string;
  first_replied_at: string | null;
  closed_at: string | null;
  creator: { id: string; display_name: string } | null;
  assignee: { id: string; display_name: string } | null;
  messages: CaseMessage[];
  qa_item_id: string | null;
  transcript_id: string | null;
  qa?: Answer | null;
  retrieval_refs?: { chunk_id: string; document_title: string; locator: string; version_label: string; source_url: string; injection_flag: boolean }[];
  events?: { kind: string; from_status: string | null; to_status: string | null; data: Record<string, unknown>; created_at: string; actor: string }[];
  notifications?: { id: string; status: string; attempts: number; last_error_code: string | null; accepted_at: string | null; created_at: string }[];
  transcript?: Transcript | null;
}

export const ROLE_LABELS: Record<string, string> = {
  caregiver: "照服員",
  supervisor: "居督",
  resident: "長輩",
  family: "家屬",
  staff: "其他",
  unknown: "未辨識",
};

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("zh-TW", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function formatMs(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// ── GA09/SC09 服務紀錄表單 ──────────────────────────────────────────────

export interface Jiaan1030FormField {
  key: string;
  label: string;
  type: "text" | "textarea" | "select" | "radio" | "checkbox" | "checkbox_group" | "date" | "time" | "number" | "signature_placeholder";
  required?: boolean;
  options?: string[];
  /** 與 options 一一對應的顯示用完整名稱；儲存值仍用 options（如 GA09/SC09 代碼）。 */
  option_labels?: string[];
  max_length?: number | null;
}

export interface Jiaan1030FormSection {
  key: string;
  label: string;
  fields: Jiaan1030FormField[];
}

export interface Jiaan1030ServiceForm {
  code: string;
  title: string;
  fields: { version: number; sections: Jiaan1030FormSection[] } | Record<string, never>;
  reviewed: boolean;
  schema_status?: "draft_unverified" | "verified_pending_approval" | "approved";
}

export interface Jiaan1030Catalog {
  ba_services: { slot: number; code: string; name: string; reviewed: boolean }[];
  service_forms: Jiaan1030ServiceForm[];
  notice: string;
}

export interface Jiaan1030ServiceDraft {
  id: string;
  service_client_id: string;
  form_code: string;
  payload: Record<string, unknown>;
  status: "draft" | "submitted";
  created_by: string;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
}

export interface Jiaan1030ServiceClient {
  id: string;
  display_label: string;
  created_at: string;
  created_by: string;
}
