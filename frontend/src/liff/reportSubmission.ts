import type { Category, CaseDetail } from '../api';
import { REPORT_SERVICES, type ReportService } from './reportServices';
import { REPORT_MODES, RECEIVING_CATEGORIES, SAFETY_EMERGENCY_CATEGORY, getReportScenarios, type ReportMode } from './reportScenarios';
export interface ClickReport {
  mode: ReportMode | null;
  service: ReportService | null;
  option: { code: string; name: string } | null;
  category: Category | null;
  templateId: string | null;
  reason: string | null;
  supplement: string;
}
export interface CasePayload {
  category_id: string; template_id: string | null; text: string;
  transcript_id: string | null; client_request_id: string;
}
export function reportText(d: ClickReport): string {
  return [
    `問題類型：${d.mode ?? ''}`,
    d.mode === '服務性問題' && d.service ? `服務項目：${d.service.code} ${d.service.name}` : '',
    d.mode === '服務性問題' && d.option ? `服務細項：${d.option.code} ${d.option.name}` : '',
    // Existing API prepends the selected template text itself.
    !d.templateId && d.reason ? `回報原因：${d.reason}` : '',
    d.supplement.trim() ? `補充說明：${d.supplement.trim()}` : '',
  ].filter(Boolean).join('\n');
}
export function buildCasePayload(d: ClickReport, requestId: string, transcriptId?: string): CasePayload {
  if (!d.mode || !REPORT_MODES.includes(d.mode) || !d.category) throw new Error('請完成問題類型與回報分類。');
  if (d.mode === '服務性問題') {
    const service = REPORT_SERVICES.find(s => s.code === d.service?.code);
    if (!service || service.name !== d.service?.name) throw new Error('請選擇服務項目。');
    if (service.options && !service.options.some(o => o.code === d.option?.code && o.name === d.option.name)) throw new Error('請選擇服務細項。');
  }
  if (!RECEIVING_CATEGORIES[d.mode].includes(d.category.name)) throw new Error('收件分類與問題類型不符。');
  if (d.templateId !== null || !getReportScenarios(d.mode,d.service?.code).some(s=>s.text===d.reason)) {
    throw new Error('請選擇此問題類型及服務適用的回報情境。');
  }
  const text = reportText(d);
  if (text.length > 1000) throw new Error('內容超過長度限制，請縮短補充說明。');
  if (requestId.length < 8 || requestId.length > 64) throw new Error('送件識別碼無效。');
  return { category_id: d.category.id, template_id: d.templateId, text,
    transcript_id: transcriptId ?? null, client_request_id: requestId };
}
export function isCreatedCase(value: unknown): value is CaseDetail {
  if (!value || typeof value !== 'object') return false;
  const c = value as Partial<CaseDetail>;
  return [c.id, c.number, c.status_label].every(v => typeof v === 'string' && !!v.trim());
}
// Separate, optional call alongside the general /api/cases report: the existing
// jiaan1030 emergency board (POST /api/jiaan1030/emergencies). Only offered for
// the 人身安全事件 scenarios; never inferred automatically from free text.
export interface EmergencyPayload {
  category: 'violence' | 'fall' | 'injury' | 'other';
  client_request_id: string;
}
export function buildEmergencyPayload(reason: string | null, requestId: string): EmergencyPayload {
  const category = reason ? SAFETY_EMERGENCY_CATEGORY[reason] : undefined;
  if (!category) throw new Error('此分類不支援標記為緊急，請改用機構既有緊急通報方式。');
  if (requestId.length < 8 || requestId.length > 64) throw new Error('緊急通報識別碼無效。');
  return { category, client_request_id: requestId };
}
