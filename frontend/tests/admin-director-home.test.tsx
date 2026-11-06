import { StrictMode } from 'react';
import { transferableAbortController } from 'node:util';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { createMemoryRouter, Navigate, RouterProvider } from 'react-router-dom';
import { AdminApp } from '../src/admin/AdminApp';
import { setToken } from '../src/api';

const token = 'test-session-token';
let role: 'admin' | 'supervisor' | 'director';
function user() {
  return { id: 'test-user', username: 'test', display_name: 'test', role,
           org: { id: 'test-org', name: 'test-org', facility_type: 'home' } };
}
function mount(path: string) {
  const router = createMemoryRouter([{ path: '/admin', element: <AdminApp />, children: [
    { index: true, element: <Navigate to="/admin/cases" replace /> },
    { path: 'cases', element: <div>案件頁</div> },
    { path: 'documents', element: <div>文件頁</div> },
  ] }], { initialEntries: [path] });
  return render(<StrictMode><RouterProvider router={router} /></StrictMode>);
}
beforeEach(() => {
  const controller = transferableAbortController();
  vi.stubGlobal('AbortController', controller.constructor);
  vi.stubGlobal('AbortSignal', controller.signal.constructor);
  sessionStorage.clear();
  setToken(token);
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    const authorization = new Headers(init?.headers).get('Authorization');
    let body: unknown; let status = 200;
    if (path === '/api/config/public') body = { dev_features: false, line_mode: 'mock', modes: { line: 'mock' } };
    else if (path === '/api/me') body = authorization === `Bearer ${token}` ? user() : (status = 401, { error: { code: 'session_expired' } });
    else if (typeof path === 'string' && path.startsWith('/api/admin/cases')) body = [];
    else return new Response(null, { status: 404 });
    return new Response(JSON.stringify(body), { status });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('director sees only authorized nav links and home content', () => {
  it('hides documents/feedback/categories links for director', async () => {
    role = 'director';
    mount('/admin/cases');
    await screen.findByText('機構監督總覽');
    expect(screen.queryByText('知識庫文件')).toBeNull();
    expect(screen.queryByText('回答回饋')).toBeNull();
    expect(screen.queryByText('問題分類設定')).toBeNull();
    expect(screen.getAllByText('BA／GA09／SC09 核准').length).toBeGreaterThan(0);
    expect(screen.getAllByText('治理指標').length).toBeGreaterThan(0);
    expect(screen.getByText('帳號與綁定')).not.toBeNull();
    expect(screen.getAllByText(/主任/).length).toBeGreaterThan(0);
  });

  it('shows documents link for supervisor (unaffected by director-only hiding)', async () => {
    role = 'supervisor';
    mount('/admin/cases');
    await screen.findByText('今日待處理');
    expect(screen.getByText('知識庫文件')).not.toBeNull();
    expect(screen.getByText('回答回饋')).not.toBeNull();
  });

  it('shows documents link for admin and renders the admin workspace', async () => {
    role = 'admin';
    mount('/admin/cases');
    await screen.findByText('系統管理導覽');
    expect(screen.getByText('知識庫文件')).not.toBeNull();
    const fieldtestLink = screen.getByText(/47 人場測管理/) as HTMLAnchorElement;
    expect(fieldtestLink.getAttribute('href')).toBe('/api/fieldtest/dashboard');
  });
});
