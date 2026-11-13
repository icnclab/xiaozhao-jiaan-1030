import { transferableAbortController } from 'node:util';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { AdminApp } from '../src/admin/AdminApp';
import { AdminDocumentsPage } from '../src/admin/pages/AdminDocumentsPage';
import { setToken } from '../src/api';

let role: 'admin' | 'supervisor' | 'director' = 'admin';
const documents = [{
  id: 'doc-1', title: '長期照顧服務法', doc_type: 'regulation', scope: 'shared', facility_types: ['home'],
  versions: [{ id: 'version-uuid', version_label: 'STUST_clean_20261010_v1', status: 'published',
    effective_from: '2026-01-01', effective_to: null, source: '衛生福利部', source_url: 'https://example.invalid',
    file_name: '長期照顧服務法.pdf', chunk_count: 119, warnings: ['法規類文件未偵測到第 1 條結構'],
    parse_error: null, missing_fields: [], uploaded_at: '2026-01-01T00:00:00Z', published_at: '2026-01-02T00:00:00Z',
    is_current: true, official_source: null }],
}];

beforeEach(() => {
  sessionStorage.clear(); setToken('test-token'); role = 'admin';
  const controller = transferableAbortController();
  vi.stubGlobal('AbortController', controller.constructor); vi.stubGlobal('AbortSignal', controller.signal.constructor);
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    let body: unknown;
    if (path === '/api/config/public') body = { dev_features: false, line_mode: 'real', modes: { line: 'real' } };
    else if (path === '/api/me') body = { id: 'actor', username: 'actor', display_name: '使用者', role, org: { id: 'org', name: '機構', facility_type: 'home' } };
    else if (path === '/api/admin/documents') body = documents;
    else if (path.startsWith('/api/admin/cases')) body = [];
    else throw new Error(`Unexpected endpoint ${path}`);
    return new Response(JSON.stringify(body));
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function mount() {
  render(<RouterProvider router={createMemoryRouter([{ path: '/admin', element: <AdminApp />, children: [
    { path: 'documents', element: <AdminDocumentsPage /> }, { path: 'login', element: <div>登入</div> },
  ] }], { initialEntries: ['/admin/documents'] })} />);
}

it('shows a human-readable document summary and pending official source', async () => {
  mount();
  const heading = await screen.findByRole('heading', { name: '長期照顧服務法' });
  const card = heading.closest('.document-card')!;
  const summary = card.querySelector('.document-summary')!;
  expect(within(card as HTMLElement).getByText('法規')).toBeTruthy();
  expect(within(summary as HTMLElement).getByText('衛生福利部')).toBeTruthy();
  expect(within(summary as HTMLElement).getByText('2026-01-01')).toBeTruthy();
  expect(within(summary as HTMLElement).getByText('待確認')).toBeTruthy();
  expect(within(summary as HTMLElement).queryByText(/STUST_clean|119|第 1 條|version-uuid/)).toBeNull();
  expect(within(card as HTMLElement).getByRole('button', { name: '查看文件' })).toBeTruthy();
});

it('keeps management controls out of the supervisor view', async () => {
  role = 'supervisor'; mount();
  await screen.findByRole('heading', { name: '長期照顧服務法' });
  expect(screen.queryByText('文件管理')).toBeNull();
  expect(screen.queryByText('管理操作與進階資訊')).toBeNull();
  expect(screen.queryByRole('button', { name: '停用' })).toBeNull();
});

it('lets director upload a pending draft without showing publish controls', async () => {
  role = 'director'; mount();
  await screen.findByRole('heading', { name: '長期照顧服務法' });
  expect(screen.getByText('建立待審草稿')).toBeTruthy();
  expect(screen.getByRole('button', { name: '上傳為待審草稿' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: '發布' })).toBeNull();
  expect(screen.queryByRole('button', { name: '停用' })).toBeNull();
});
