import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ReportPreviewPage } from '../src/liff/pages/ReportPreviewPage';
import { getReportScenarios, SAFETY_EMERGENCY_CATEGORY } from '../src/liff/reportScenarios';
import { buildEmergencyPayload } from '../src/liff/reportSubmission';
import { setToken } from '../src/api';

// 10/30 嘉安訪談第六輪：照服員快速分類回報（性騷擾／不當觸碰、暴力／人身安全、跌倒、傷口／異常狀況）。
// 一律先建立一般案件（沿用既有 /api/cases），只有使用者明確勾選並確認後，才額外呼叫既有
// 緊急通報 /api/jiaan1030/emergencies；不勾選則完全不呼叫該端點。
const categories = [
  { id: 'cat-incident', name: '事件處理規範', description: null, templates: [] },
  { id: 'cat-other', name: '其他', description: null, templates: [] },
];
const createdCase = { id: 'case-safety', number: 'C-SAFE-001', status_label: '待處理', assignee: null };
const createdEmergency = { id: 'em-1', category: 'violence', status: 'open', created_at: new Date().toISOString(), acknowledged_at: null, resolved_at: null, created_by: 'u1', acknowledged_by: null, resolved_by: null, delivery: 'web_poll_only' };
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const fetchMock = vi.fn();
let emergencyResponse: () => Promise<Response>;
beforeEach(() => {
  emergencyResponse = async () => response(createdEmergency);
  fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path === '/api/categories') return response(categories);
    if (path === '/api/cases' && init?.method === 'POST') return response(createdCase);
    if (path === '/api/jiaan1030/emergencies' && init?.method === 'POST') return emergencyResponse();
    throw new Error('Unexpected offline request blocked');
  });
  vi.stubGlobal('fetch', fetchMock);
  setToken('isolated-test-only');
});
afterEach(() => { cleanup(); setToken(null); vi.unstubAllGlobals(); vi.clearAllMocks(); });
function open() { render(<MemoryRouter><ReportPreviewPage /></MemoryRouter>); }
function click(name: string | RegExp) { fireEvent.click(screen.getByRole('button', { name })); }
const emergencyPosts = () => fetchMock.mock.calls.filter(([p, init]) => p === '/api/jiaan1030/emergencies' && init?.method === 'POST');
const casePosts = () => fetchMock.mock.calls.filter(([p, init]) => p === '/api/cases' && init?.method === 'POST');

async function selectScenario(text: string) {
  click('人身安全事件');
  await waitFor(() => expect(screen.queryByText('收件資料載入中…')).toBeNull());
  click(text);
}

it('shows all four quick-classification types and no unrelated scenarios', async () => {
  open(); click('人身安全事件');
  await waitFor(() => expect(screen.queryByText('收件資料載入中…')).toBeNull());
  for (const s of getReportScenarios('人身安全事件')) expect(screen.getByRole('button', { name: s.text })).toBeTruthy();
  expect(getReportScenarios('人身安全事件').map(s => s.text)).toEqual(['性騷擾／不當觸碰', '暴力／人身安全', '跌倒', '傷口／異常狀況']);
});

it('unchecked emergency box creates only a general case, never calls emergency endpoint', async () => {
  open(); await selectScenario('跌倒'); click('下一步：確認內容'); click('確認送出回報');
  await screen.findByText('案件已建立');
  expect(casePosts()).toHaveLength(1);
  expect(emergencyPosts()).toHaveLength(0);
});

it('checking the box and confirming also sends the existing emergency report with mapped category', async () => {
  open(); await selectScenario('暴力／人身安全');
  fireEvent.click(screen.getByRole('checkbox'));
  click('下一步：確認內容'); click('確認送出回報');
  await screen.findByText(/已同時送出人身安全事件通知/);
  expect(emergencyPosts()).toHaveLength(1);
  expect(JSON.parse(String(emergencyPosts()[0][1]?.body)).category).toBe('violence');
});

it('maps each of the four types to the existing emergency categories (sexual harassment has no dedicated code, so other)', () => {
  expect(SAFETY_EMERGENCY_CATEGORY['性騷擾／不當觸碰']).toBe('other');
  expect(SAFETY_EMERGENCY_CATEGORY['暴力／人身安全']).toBe('violence');
  expect(SAFETY_EMERGENCY_CATEGORY['跌倒']).toBe('fall');
  expect(SAFETY_EMERGENCY_CATEGORY['傷口／異常狀況']).toBe('injury');
});

it('does not require retyping to confirm; back then forward keeps emergency checkbox reset on scenario change', async () => {
  open(); await selectScenario('跌倒');
  fireEvent.click(screen.getByRole('checkbox'));
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true);
  click('傷口／異常狀況');
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
});

it('surfaces emergency failure without claiming the emergency notice succeeded, while keeping the case created', async () => {
  emergencyResponse = async () => response({ error: { code: 'down' } }, 500);
  open(); await selectScenario('傷口／異常狀況');
  fireEvent.click(screen.getByRole('checkbox'));
  click('下一步：確認內容'); click('確認送出回報');
  await screen.findByText('案件已建立');
  await screen.findByText(/緊急通報未能確認送出/);
  expect(screen.queryByText(/已同時送出人身安全事件通知/)).toBeNull();
});

it('buildEmergencyPayload rejects a reason outside the four known types', () => {
  expect(() => buildEmergencyPayload('不存在的分類', 'isolated-request-id')).toThrow();
  expect(() => buildEmergencyPayload(null, 'isolated-request-id')).toThrow();
});
