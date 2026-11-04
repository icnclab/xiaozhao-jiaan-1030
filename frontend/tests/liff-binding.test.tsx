import { transferableAbortController } from 'node:util';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { LiffApp, pendingBinding, useLiff } from '../src/liff/LiffApp';
import { BindPage } from '../src/liff/pages/BindPage';
import { AskPage } from '../src/liff/pages/AskPage';
import { RecordPage } from '../src/liff/pages/RecordPage';
import { ReportPage } from '../src/liff/pages/ReportPage';
import { CasesPage } from '../src/liff/pages/CasesPage';
import { getToken } from '../src/api';

const sdk = vi.hoisted(() => ({init:vi.fn(async()=>undefined),isLoggedIn:vi.fn(()=>true),
  getIDToken:vi.fn(()=>'test-line-id-token'),login:vi.fn()}));
vi.mock('@line/liff',()=>({default:sdk}));
const config={line_mode:'real',liff_id:'test-liff-id',dev_features:false,modes:{line:'real'},bot_name:'小照',
  wake_words:['小照'],limits:{question_max_sec:60,conversation_max_sec:600,max_upload_mb:30}};
const user={id:'test-caregiver',username:'test_cg',display_name:'測試照服員',role:'caregiver',org:{id:'test-org',name:'測試',facility_type:'home'}};
let bound:boolean;let invalidCode:boolean;let requests:string[];let bindingBody:unknown;
function Home(){const {user}=useLiff();return <div>已登入 {user.display_name}</div>;}
function mount(path:string){
  const router=createMemoryRouter([{path:'/liff',element:<LiffApp/>,children:[
    {index:true,element:<Home/>},{path:'bind',element:<BindPage/>},
    {path:'ask',element:<AskPage/>},{path:'record',element:<RecordPage/>},
    {path:'report',element:<ReportPage/>},{path:'cases',element:<CasesPage/>},
  ]}],{initialEntries:[path]});
  render(<RouterProvider router={router}/>);return router;
}
beforeEach(()=>{
  sessionStorage.clear();pendingBinding.idToken=null;bound=false;invalidCode=false;requests=[];bindingBody=null;
  vi.clearAllMocks();const controller=transferableAbortController();
  vi.stubGlobal('AbortController',controller.constructor);vi.stubGlobal('AbortSignal',controller.signal.constructor);
  vi.stubGlobal('fetch',vi.fn(async(path:string,init?:RequestInit)=>{
    requests.push(path);let status=200;let body:unknown;
    if(path==='/api/config/public') body=config;
    else if(path==='/api/auth/liff') body=bound?{status:'ok',session_token:'test-session',user,dev:false}:{status:'needs_binding',dev:false};
    else if(path==='/api/auth/liff/bind'){
      bindingBody=JSON.parse(String(init?.body));
      if(invalidCode){status=400;body={error:{code:'invalid_code',message:'綁定碼無效或已過期'}};}
      else body={status:'ok',session_token:'test-session',user};
    }
    else if(['/api/categories','/api/cases/mine','/api/transcripts'].includes(path)) body=[];
    else throw new Error('Unexpected API: '+path);
    return new Response(JSON.stringify(body),{status});
  }));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
describe.each(['ask','record','report','cases'])('unbound /%s',entry=>{
  it('redirects before mounting the entry and displays the same Traditional Chinese binding page',async()=>{
    const router=mount('/liff/'+entry);
    await screen.findByRole('heading',{name:'綁定帳號'});
    expect(router.state.location.pathname).toBe('/liff/bind');
    expect(screen.getByText('請輸入 8 碼綁定碼，將「本人」的 LINE 與機構帳號連結。照服員可向督導領取；督導、主任及管理員需由具權限的人員在後台核發。')).toBeTruthy();
    expect(screen.getByRole('button',{name:'綁定'})).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\uFFFD|LiffContext missing|Unexpected Application Error/);
    expect(requests).toEqual(['/api/config/public','/api/auth/liff']);
    expect(sdk.init).toHaveBeenCalledWith({liffId:'test-liff-id'});
    expect(pendingBinding.idToken).toBe('test-line-id-token');expect(getToken()).toBeNull();
  });
});
describe.each([['ask','問 AI'],['record','錄音／談話紀錄'],['report','問題分類回報'],['cases','我的案件']])('bound /%s', (entry,heading)=>{
  it('keeps the original entry available',async()=>{
    bound=true;const router=mount('/liff/'+entry);
    await screen.findByRole('heading',{name:heading});
    expect(router.state.location.pathname).toBe('/liff/'+entry);
    expect(screen.queryByRole('heading',{name:'綁定帳號'})).toBeNull();
  });
});
it('passes the unchanged LINE ID token and binding code to the API and enters the bound home',async()=>{
  const router=mount('/liff/ask');await screen.findByRole('heading',{name:'綁定帳號'});
  fireEvent.change(screen.getByPlaceholderText('例如 AB3K7X9P'),{target:{value:'AB3K7X9P'}});
  fireEvent.click(screen.getByRole('button',{name:'綁定'}));
  await screen.findByText('已登入 測試照服員');expect(router.state.location.pathname).toBe('/liff');
  expect(bindingBody).toEqual({id_token:'test-line-id-token',binding_code:'AB3K7X9P'});
  expect(getToken()).toBe('test-session');
});
it('shows a readable invalid-code API error without entering protected pages',async()=>{
  invalidCode=true;const router=mount('/liff/record');await screen.findByRole('heading',{name:'綁定帳號'});
  fireEvent.change(screen.getByPlaceholderText('例如 AB3K7X9P'),{target:{value:'AB3K7X9P'}});
  fireEvent.click(screen.getByRole('button',{name:'綁定'}));
  await screen.findByText('綁定碼無效或已過期');expect(router.state.location.pathname).toBe('/liff/bind');expect(getToken()).toBeNull();
});
