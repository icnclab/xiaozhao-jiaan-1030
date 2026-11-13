import { transferableAbortController } from 'node:util';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { AdminApp } from '../src/admin/AdminApp';
import { AdminAuditPage } from '../src/admin/pages/AdminAuditPage';
import { setToken } from '../src/api';

const auditRows = [
  { id: 1, created_at: '2026-11-12T00:00:00Z', action: 'qa.ask', outcome: 'ok', actor_role: 'supervisor', actor: 'sup_a', target_type: 'qa_item', target_id: 'abc-123', meta: {} },
  { id: 2, created_at: '2026-11-12T00:01:00Z', action: 'source.download', outcome: 'ok', actor_role: 'admin', actor: 'admin_happy', target_type: 'document_version', target_id: 'def-456', meta: {} },
];

beforeEach(() => {
  sessionStorage.clear(); setToken('test-token');
  const controller = transferableAbortController();
  vi.stubGlobal('AbortController', controller.constructor); vi.stubGlobal('AbortSignal', controller.signal.constructor);
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    let body: unknown;
    if (path === '/api/config/public') body = { dev_features: false, line_mode: 'real', modes: { line: 'real' } };
    else if (path === '/api/me') body = { id: 'admin_happy', username: 'admin_happy', display_name: '管理員', role: 'admin', org: { id: 'org', name: '幸福園', facility_type: 'residential' } };
    else if (path === '/api/admin/audit') body = auditRows;
    else throw new Error('Unexpected endpoint ' + path);
    return new Response(JSON.stringify(body));
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('shows a simplified Chinese operation log without technical targets or metadata', async () => {
  render(<RouterProvider router={createMemoryRouter([{ path: '/admin', element: <AdminApp />, children: [
    { path: 'audit', element: <AdminAuditPage /> }, { path: 'login', element: <div>登入頁</div> },
  ] }], { initialEntries: ['/admin/audit'] })} />);
  expect(await screen.findByText('AI問答')).toBeTruthy();
  await waitFor(() => expect(screen.getAllByText('下載引用文件')).toHaveLength(2));
  expect(screen.getByRole('heading', { name: '操作紀錄' })).toBeTruthy();
  expect(screen.getAllByText('成功').length).toBe(2);
  expect(screen.getByText('督導')).toBeTruthy();
  // 原始技術代碼、UUID與詳細JSON不出現在一般介面。
  expect(screen.queryByText('qa.ask', { selector: 'td' })).toBeNull();
  expect(screen.queryByText('詳細資訊')).toBeNull();
  expect(screen.queryByText('abc-123')).toBeNull();
  expect(screen.queryByText('qa_item')).toBeNull();
});
