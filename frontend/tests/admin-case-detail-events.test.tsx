import { StrictMode } from 'react';
import { transferableAbortController } from 'node:util';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { AdminApp } from '../src/admin/AdminApp';
import { AdminCaseDetailPage } from '../src/admin/pages/AdminCaseDetailPage';
import { setToken } from '../src/api';

const token = 'test-session-token';

function user() {
  return { id: 'sup-1', username: 'sup', display_name: 'sup', role: 'supervisor' as const,
           org: { id: 'org-1', name: 'org-1', facility_type: 'home' } };
}

function caseDetail() {
  return {
    id: 'case-1', number: 'C-0001', status: 'closed', status_label: '已結案',
    source: 'quick_report', source_label: '分類回報', category: null,
    summary_masked: '摘要', reason: '原因', created_at: '2026-11-05T00:00:00Z',
    updated_at: '2026-11-05T00:00:00Z', first_replied_at: null, closed_at: '2026-11-05T01:00:00Z',
    creator: { id: 'care-1', display_name: '照服員A' }, assignee: { id: 'sup-1', display_name: 'sup' },
    messages: [], qa_item_id: null, transcript_id: null,
    events: [
      { kind: 'created', from_status: null, to_status: 'pending', data: {}, created_at: '2026-11-05T00:00:00Z', actor: '照服員A' },
      { kind: 'closed', from_status: 'in_progress', to_status: 'closed', data: { reason: '已處理完畢' }, created_at: '2026-11-05T01:00:00Z', actor: 'sup' },
    ],
    notifications: [],
  };
}

function mount() {
  const router = createMemoryRouter([{ path: '/admin', element: <AdminApp />, children: [
    { path: 'cases/:id', element: <AdminCaseDetailPage /> },
    { path: 'users', element: <div>users</div> },
  ] }], { initialEntries: ['/admin/cases/case-1'] });
  return render(<StrictMode><RouterProvider router={router} /></StrictMode>);
}

beforeEach(() => {
  const controller = transferableAbortController();
  vi.stubGlobal('AbortController', controller.constructor);
  vi.stubGlobal('AbortSignal', controller.signal.constructor);
  sessionStorage.clear();
  setToken(token);
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    let body: unknown; let status = 200;
    if (path === '/api/config/public') body = { dev_features: false, line_mode: 'mock', modes: { line: 'mock' } };
    else if (path === '/api/me') body = user();
    else if (path === '/api/admin/cases/case-1') body = caseDetail();
    else if (path === '/api/admin/users') body = [];
    else { status = 404; body = { error: { code: 'not_found' } }; }
    return new Response(JSON.stringify(body), { status });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('case detail event history shows human-readable labels', () => {
  it('shows friendly event/status labels instead of raw kind/JSON, with a reason suffix on close', async () => {
    mount();
    await screen.findByText('C-0001');
    fireEvent.click(screen.getByText(/查看處理歷程/));
    expect(await screen.findByText('建立案件')).not.toBeNull();
    expect(screen.getByText('已完成結案：已處理完畢')).not.toBeNull();
    expect(screen.queryByText('created')).toBeNull();
    expect(screen.queryByText(/"reason"/)).toBeNull();
  });
});
