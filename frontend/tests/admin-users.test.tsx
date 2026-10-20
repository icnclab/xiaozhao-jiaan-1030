import { transferableAbortController } from 'node:util';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { AdminApp } from '../src/admin/AdminApp';
import { AdminUsersPage } from '../src/admin/pages/AdminUsersPage';
import { setToken } from '../src/api';

let role = 'admin';
const row = (name: string, userRole = 'caregiver', active = true, bound = false) => ({id:name,username:name,display_name:name,role:userRole,is_active:active,line_bound:bound,line_blocked:false});
const rows = [row('jiaan_admin','admin'),row('jiaan_cg01','caregiver',true,true),...['jiaan_cg02','jiaan_cg03','jiaan_cg04'].map(name=>row(name)),row('jiaan_sv01','supervisor',true,true),row('jiaan_sv02','supervisor'),...['test_cg01','test_cg02','test_cg03'].map(name=>row(name)),row('test_sv001','supervisor'),row('test_disabled','caregiver',false)];
beforeEach(() => {
  role = 'admin';sessionStorage.clear();setToken('test-token');
  const controller = transferableAbortController();
  vi.stubGlobal('AbortController',controller.constructor);vi.stubGlobal('AbortSignal',controller.signal.constructor);
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    let body: unknown;
    if(path === '/api/config/public') body={dev_features:false,line_mode:'real',modes:{line:'real'}};
    else if(path === '/api/me') body={id:'jiaan_admin',username:'jiaan_admin',display_name:'actor',role,org:{id:'org',name:'org',facility_type:'home'}};
    else if(path === '/api/admin/users') body=rows;
    else if(path === '/api/admin/users?include_deleted=true') body=[...rows,{...row('__deleted__123','caregiver',false),is_deleted:true,original_username:'test_deleted'}];
    else throw new Error('Unexpected endpoint '+path);
    return new Response(JSON.stringify(body));
  }));
});
afterEach(() => {cleanup();vi.unstubAllGlobals();});
function renderPage() {
  render(<RouterProvider router={createMemoryRouter([{path:'/admin',element:<AdminApp/>,children:[{path:'users',element:<AdminUsersPage/>},{path:'login',element:<div>登入頁</div>}]}],{initialEntries:['/admin/users']})}/>);
}
async function mount() {
  renderPage();
  await screen.findByRole('region',{name:'嘉安正式帳號'});
}
function account(name:string) { return within(screen.getAllByText(name).find(el=>el.tagName==='TD')!.closest('tr')!); }
it('groups prefixes and hides inactive accounts by default',async()=>{
  await mount();
  expect(within(screen.getByRole('region',{name:'嘉安正式帳號'})).getAllByText('jiaan_cg01').length).toBeGreaterThan(0);
  expect(within(screen.getByRole('region',{name:'內部測試帳號'})).getAllByText('test_cg01').length).toBeGreaterThan(0);
  expect(screen.queryByText('test_disabled')).toBeNull();expect(screen.queryByText('test_deleted')).toBeNull();
});
it('toggle includes inactive and deleted original names; deleted accounts have no actions',async()=>{
  await mount();fireEvent.click(screen.getByRole('checkbox',{name:'顯示停用／已刪除帳號'}));
  await screen.findAllByText('test_deleted');
  expect(account('test_deleted').getByText('已刪除')).toBeTruthy();expect(account('test_deleted').queryByRole('button')).toBeNull();
  expect(account('test_disabled').getByText('停用')).toBeTruthy();
  fireEvent.click(screen.getByRole('checkbox',{name:'顯示停用／已刪除帳號'}));
  expect(screen.queryByText('test_deleted')).toBeNull();expect(screen.queryByText('test_disabled')).toBeNull();
});
it('admin has one primary action and collapsed permitted secondary actions',async()=>{
  await mount();const cg=account('jiaan_cg01');
  expect(cg.getByRole('button',{name:'產生綁定碼'})).toBeTruthy();expect(cg.queryByRole('button',{name:'刪除帳號'})).toBeNull();
  fireEvent.click(cg.getByRole('button',{name:'jiaan_cg01 更多'}));
  for(const name of ['停用','解除 LINE 綁定','刪除帳號']) expect(cg.getByRole('button',{name})).toBeTruthy();
  fireEvent.click(account('jiaan_admin').getByRole('button',{name:'jiaan_admin 更多'}));
  expect(account('jiaan_admin').queryByRole('button',{name:'刪除帳號'})).toBeNull();
  expect(account('jiaan_sv01').queryByRole('button',{name:'產生綁定碼'})).toBeNull();
});
it('supervisor only has caregiver binding/unbinding, no account management or non-caregiver menu',async()=>{
  role='supervisor';await mount();
  expect(screen.queryByText('新增帳號')).toBeNull();
  const cg=account('jiaan_cg01');fireEvent.click(cg.getByRole('button',{name:'jiaan_cg01 更多'}));
  expect(cg.getByRole('button',{name:'解除 LINE 綁定'})).toBeTruthy();
  expect(cg.queryByRole('button',{name:'停用'})).toBeNull();expect(cg.queryByRole('button',{name:'刪除帳號'})).toBeNull();
  expect(account('jiaan_sv01').queryByRole('button')).toBeNull();expect(account('test_cg01').queryByRole('button',{name:/更多/})).toBeNull();
});
it('inactive accounts offer enable to admin; unbound accounts do not offer unbind',async()=>{
  await mount();fireEvent.click(screen.getByRole('checkbox',{name:'顯示停用／已刪除帳號'}));await screen.findAllByText('test_disabled');
  const cg=account('test_disabled');expect((cg.getByRole('button',{name:'產生綁定碼'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(cg.getByRole('button',{name:'test_disabled 更多'}));expect(cg.getByRole('button',{name:'啟用'})).toBeTruthy();expect(cg.queryByRole('button',{name:'解除 LINE 綁定'})).toBeNull();
});
it('caregiver cannot enter account management',async()=>{
  role='caregiver';renderPage();await screen.findByText('登入頁');
  expect(screen.queryByRole('heading',{name:'帳號與 LINE 綁定'})).toBeNull();
  expect(screen.queryByRole('checkbox')).toBeNull();
});
