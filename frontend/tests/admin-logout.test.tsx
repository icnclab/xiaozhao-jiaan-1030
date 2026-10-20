import { StrictMode } from 'react';
import { transferableAbortController } from 'node:util';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, Navigate, RouterProvider } from 'react-router-dom';
import { AdminApp, useAdmin } from '../src/admin/AdminApp';
import { AdminLoginPage } from '../src/admin/pages/AdminLoginPage';
import { AdminUsersPage } from '../src/admin/pages/AdminUsersPage';
import { getToken, setToken } from '../src/api';

const token = 'test-session-token';
let role: 'admin' | 'supervisor';
let revoked: boolean;
let logoutAuthorization: string | null;
let meCalls: number;
let failLogout: boolean;
function user() { return { id:'test-user', username:'test', display_name:'test', role, org:{id:'test-org',name:'test-org',facility_type:'home'} }; }
function ProtectedPage() { const { user } = useAdmin(); return <div>protected {user.role}</div>; }
function mount(path: string) {
  const router = createMemoryRouter([{path:'/admin',element:<AdminApp />,children:[
    {index:true,element:<Navigate to='/admin/cases' replace />},
    {path:'login',element:<AdminLoginPage />},
    {path:'cases',element:<ProtectedPage />},
    {path:'users',element:<AdminUsersPage />},
  ]}],{initialEntries:[path]});
  const view=render(<StrictMode><RouterProvider router={router}/></StrictMode>);
  return {router,view};
}
beforeEach(() => {
  // Node Request and jsdom's AbortSignal are different realms. Router requests
  // must use the matching Node constructors; no app/browser behavior is mocked.
  const controller = transferableAbortController();
  vi.stubGlobal('AbortController', controller.constructor);
  vi.stubGlobal('AbortSignal', controller.signal.constructor);
  sessionStorage.clear();role='admin';revoked=false;logoutAuthorization=null;meCalls=0;failLogout=false;
  vi.stubGlobal('fetch',vi.fn(async (path: string, init?: RequestInit) => {
    const authorization=new Headers(init?.headers).get('Authorization');
    let body: unknown;let status=200;
    if(path==='/api/config/public') body={dev_features:false,line_mode:'real',modes:{line:'real'}};
    else if(path==='/api/me') { meCalls++; if(revoked || authorization!==`Bearer ${token}`) {status=401;body={error:{code:'session_expired'}};} else body=user(); }
    else if(path==='/api/admin/users') body=[];
    else if(path==='/api/auth/logout') {
      logoutAuthorization=authorization;
      if(failLogout) throw new Error('network');
      revoked=true;status=204;
    }
    else if(path==='/api/auth/login') {revoked=false;body={session_token:token,user:user()};}
    else throw new Error('Unexpected endpoint: '+path);
    return new Response(status===204?null:JSON.stringify(body),{status});
  }));
});
afterEach(() => {cleanup();vi.unstubAllGlobals();});

describe.each(['admin','supervisor'] as const)('%s logout', (actor) => {
  it('leaves the context-dependent account page directly and clears token with authenticated revoke request', async () => {
    role=actor;setToken(token);const {router}=mount('/admin/users');
    await screen.findByText('帳號與 LINE 綁定');
    fireEvent.click(screen.getByText('登出'));
    await screen.findByText('督導後台登入');
    expect(router.state.location.pathname).toBe('/admin/login');
    expect(getToken()).toBeNull();expect(sessionStorage.getItem('ltc_session')).toBeNull();
    expect(logoutAuthorization).toBe(`Bearer ${token}`);expect(revoked).toBe(true);
    expect(screen.queryByText('帳號與 LINE 綁定')).toBeNull();
    expect(screen.queryByText(/AdminContext missing|Unexpected Application Error/)).toBeNull();
  });
  it('refresh after logout and direct /admin both require login without protected renders', async () => {
    role=actor;setToken(token);let mounted=mount('/admin/users');
    await screen.findByText('帳號與 LINE 綁定');fireEvent.click(screen.getByText('登出'));
    await screen.findByText('督導後台登入');mounted.view.unmount();
    const calls=meCalls;
    mounted=mount('/admin/login');await screen.findByText('督導後台登入');mounted.view.unmount();
    mounted=mount('/admin');await screen.findByText('督導後台登入');
    expect(mounted.router.state.location.pathname).toBe('/admin/login');expect(meCalls).toBe(calls);
    expect(getToken()).toBeNull();expect(screen.queryByText(/protected/)).toBeNull();
  });
  it('can log in again normally after logout', async () => {
    role=actor;setToken(token);const {router}=mount('/admin/users');
    await screen.findByText('帳號與 LINE 綁定');fireEvent.click(screen.getByText('登出'));
    await screen.findByText('督導後台登入');
    fireEvent.change(screen.getByPlaceholderText('帳號'),{target:{value:'test'}});
    fireEvent.change(screen.getByPlaceholderText('密碼'),{target:{value:'test-password'}});
    fireEvent.click(screen.getByRole('button',{name:'登入'}));
    await screen.findByText(`protected ${actor}`);
    expect(router.state.location.pathname).toBe('/admin/cases');expect(getToken()).toBe(token);
  });
});
it('expired session clears token and redirects before rendering protected children', async () => {
  setToken(token);revoked=true;const {router}=mount('/admin/users');
  await screen.findByText('督導後台登入');expect(router.state.location.pathname).toBe('/admin/login');
  expect(getToken()).toBeNull();expect(screen.queryByText('帳號與 LINE 綁定')).toBeNull();
});
it('local logout still completes when server revoke is unreachable', async () => {
  setToken(token);failLogout=true;const {router}=mount('/admin/users');
  await screen.findByText('帳號與 LINE 綁定');fireEvent.click(screen.getByText('登出'));
  await waitFor(()=>expect(router.state.location.pathname).toBe('/admin/login'));
  expect(getToken()).toBeNull();await screen.findByText('督導後台登入');
});
