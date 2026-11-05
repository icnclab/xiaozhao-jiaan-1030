import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ReportPreviewPage } from '../src/liff/pages/ReportPreviewPage';
import { getReportScenarios, resolveReceivingCategory, REPORT_MODES, SCENARIO_SOURCES } from '../src/liff/reportScenarios';
import { buildCasePayload, type ClickReport } from '../src/liff/reportSubmission';
import { REPORT_SERVICES } from '../src/liff/reportServices';
import { setToken } from '../src/api';

const names=['家屬額外要求','服務範圍','移位與行動協助','沐浴與清潔','飲食與餵食','事件處理規範','紀錄與申報規範','其他'];
const categories=names.map((name,i)=>({id:`00000000-0000-4000-8000-${String(i+1).padStart(12,'0')}`,name,description:null,templates:[{id:`old-template-${i}`,text:`舊通用模板-${name}`}]}));
const created={id:'case-isolated',number:'C-TEST-001',status_label:'待處理',assignee:null};
const response=(body:unknown,status=200)=>new Response(JSON.stringify(body),{status});
const fetchMock=vi.fn();let createResponse:()=>Promise<Response>;
beforeEach(()=>{
 createResponse=async()=>response(created);
 fetchMock.mockImplementation(async(path:string,init?:RequestInit)=>{
  if(path==='/api/categories')return response(categories);
  if(path==='/api/cases' && init?.method==='POST')return createResponse();
  throw new Error('Unexpected offline request blocked');
 });
 vi.stubGlobal('fetch',fetchMock);setToken('isolated-test-only');
});
afterEach(()=>{cleanup();setToken(null);vi.unstubAllGlobals();vi.clearAllMocks();});
function open(){render(<MemoryRouter><ReportPreviewPage/></MemoryRouter>);}
function click(name:string|RegExp){fireEvent.click(screen.getByRole('button',{name}));}
const posts=()=>fetchMock.mock.calls.filter(([p,init])=>p==='/api/cases' && init?.method==='POST');
const payload=()=>JSON.parse(String(posts()[0][1]?.body));
async function choose(mode:typeof REPORT_MODES[number]='服務性問題',code='BA01'){
 click(mode);
 if(mode==='服務性問題')click(new RegExp(code));
 await waitFor(()=>expect(screen.queryByText('收件資料載入中…')).toBeNull());
 click(getReportScenarios(mode,code)[0].text);click('下一步：確認內容');
}

it.each(REPORT_MODES)('shows only matching scenarios, never old category or template buttons: %s',async mode=>{
 open();click(mode);if(mode==='服務性問題')click(/BA01/);
 await waitFor(()=>expect(screen.queryByText('收件資料載入中…')).toBeNull());
 for(const name of names)expect(screen.queryByRole('button',{name,exact:true})).toBeNull();
 for(const c of categories)expect(screen.queryByRole('button',{name:c.templates[0].text})).toBeNull();
 for(const s of getReportScenarios(mode,'BA01'))expect(screen.getByRole('button',{name:s.text})).toBeTruthy();
 for(const other of REPORT_MODES.filter(m=>m!==mode))for(const s of getReportScenarios(other,'BA03')){
  expect(screen.queryByRole('button',{name:s.text})).toBeNull();
 }
 expect(posts()).toHaveLength(0);
});
it.each(REPORT_MODES)('allows no supplemental text and uses existing request schema: %s',async mode=>{
 open();await choose(mode);expect(posts()).toHaveLength(0);click('確認送出回報');await screen.findByText('案件已建立');
 const body=payload();expect(Object.keys(body).sort()).toEqual(['category_id','client_request_id','template_id','text','transcript_id']);
 expect(body.category_id).toBe(resolveReceivingCategory(mode,categories)!.id);expect(body.template_id).toBeNull();
 expect(body.text).toContain('問題類型：'+mode);expect(body.text).toContain('回報原因：');expect(body.text).not.toContain('補充說明：');
 expect(new Headers(posts()[0][1]?.headers).get('Authorization')).toBe('Bearer isolated-test-only');
});
it('explicitly discloses authorized complaint-to-other compatibility route',async()=>{
 open();await choose('申訴處理');expect(screen.getByText(/將沿用「其他」既有居督收件流程/)).toBeTruthy();
 expect(screen.getByText(/不代表正式申訴已受理/)).toBeTruthy();
});
it('BA03 does not show meal, housework or complaint scenarios',async()=>{
 open();click('服務性問題');click(/BA03/);
 expect(screen.getByRole('button',{name:'測量設備無法正常使用'})).toBeTruthy();
 expect(screen.queryByRole('button',{name:'代購清單或交付內容不清楚'})).toBeNull();
 expect(screen.queryByRole('button',{name:'反映收費、收據或自費說明爭議'})).toBeNull();
});
it('preserves selections on confirmation back and clears incompatible reason on service change',async()=>{
 open();await choose();click('返回修改');
 expect(screen.getByRole('button',{name:getReportScenarios('服務性問題','BA01')[0].text}).getAttribute('aria-pressed')).toBe('true');
 click('上一步');click(/BA03/);
 expect(screen.queryByRole('button',{name:getReportScenarios('服務性問題','BA01')[0].text})).toBeNull();
 expect((screen.getByRole('button',{name:'下一步：確認內容'}) as HTMLButtonElement).disabled).toBe(true);
});
it('preserves service suboption, selection and blank supplement',async()=>{
 open();click('服務性問題');click('下一頁');click(/BA15/);click('self 自用');
 await waitFor(()=>expect(screen.queryByText('收件資料載入中…')).toBeNull());
 click(getReportScenarios('服務性問題','BA15')[0].text);click('下一步：確認內容');click('確認送出回報');
 await screen.findByText('案件已建立');expect(payload().text).toContain('服務細項：self 自用');
});
it.each([401,403,422,503])('never claims success on %s; same-payload/id retry',async status=>{
 createResponse=async()=>response({error:{code:'isolated',message:'測試錯誤'}},status);
 open();await choose();click('確認送出回報');await screen.findByRole('alert');
 expect(screen.queryByText('案件已建立')).toBeNull();click('重試送出');await waitFor(()=>expect(posts()).toHaveLength(2));
 expect(posts()[0][1]?.body).toBe(posts()[1][1]?.body);await screen.findByRole('button',{name:'重試送出'});
});
it('successful retry after lost connection keeps original key',async()=>{
 createResponse=async()=>{throw new TypeError('offline');};open();await choose();click('確認送出回報');await screen.findByRole('alert');
 createResponse=async()=>response(created);click('重試送出');await screen.findByText('案件已建立');
 expect(posts()[0][1]?.body).toBe(posts()[1][1]?.body);
});
it('blocks double submission while pending',async()=>{
 let finish!:(value:Response)=>void;createResponse=()=>new Promise(r=>{finish=r;});
 open();await choose();click('確認送出回報');click('送出中…');expect(posts()).toHaveLength(1);
 finish(response(created));await screen.findByText('案件已建立');
});
it('rejects malformed success response',async()=>{
 createResponse=async()=>response({});open();await choose();click('確認送出回報');await screen.findByRole('alert');
 expect(screen.queryByText('案件已建立')).toBeNull();
});
it('missing receiving category blocks submission instead of choosing a random category',async()=>{
 fetchMock.mockResolvedValueOnce(response([categories[2]]));open();click('額外要求');
 await screen.findByRole('alert');click(getReportScenarios('額外要求')[0].text);
 expect((screen.getByRole('button',{name:'下一步：確認內容'}) as HTMLButtonElement).disabled).toBe(true);expect(posts()).toHaveLength(0);
});
it('does not route missing service category to Other or unrelated categories',()=>{
 expect(resolveReceivingCategory('服務性問題',[categories[0],categories[7]])).toBeNull();
 expect(resolveReceivingCategory('額外要求',[categories[7]])).toBeNull();
 expect(resolveReceivingCategory('申訴處理',[categories[7]])?.name).toBe('其他');
});
it('prefers dedicated complaint category over explicitly authorized Other fallback',()=>{
 const specific={...categories[7],id:'dedicated',name:'申訴處理'};
 expect(resolveReceivingCategory('申訴處理',[categories[7],specific])?.id).toBe('dedicated');
 expect(resolveReceivingCategory('申訴處理',[specific,{...specific,id:'duplicate'}])).toBeNull();
});
it.each([401,403,500])('load failure %s is explicit and retryable',async status=>{
 fetchMock.mockResolvedValueOnce(response({error:{code:'load'}},status));open();click('額外要求');await screen.findByRole('alert');
 click('重新載入');await waitFor(()=>expect(screen.queryByRole('alert')).toBeNull());
});
it('keeps safety reminder and complaint escalation boundary visible',async()=>{
 open();click('申訴處理');expect(screen.getByText(/緊急或有人身安全風險/)).toBeTruthy();
 expect(screen.getByText(/若需迴避被反映人員/)).toBeTruthy();
});
it('rejects mismatched modes, unrelated templates, overlength text and missing suboptions',()=>{
 const draft:ClickReport={mode:'服務性問題',service:REPORT_SERVICES[0],option:null,category:categories[1],templateId:null,reason:getReportScenarios('服務性問題','BA01')[0].text,supplement:''};
 for(const bad of [{...draft,reason:getReportScenarios('申訴處理')[0].text},{...draft,templateId:'old-template-1'}, {...draft,category:categories[0]}, {...draft,supplement:'字'.repeat(1000)}, {...draft,service:REPORT_SERVICES.find(s=>s.code==='BA17')!}]) {
  expect(()=>buildCasePayload(bad,'isolated-request')).toThrow();
 }
});
it.each(REPORT_SERVICES)('keeps $code service and provides supported service-only scenarios', service=>{
 const scenarios=getReportScenarios('服務性問題',service.code);expect(scenarios.length).toBeGreaterThan(0);
 expect(new Set(scenarios.map(s=>s.id)).size).toBe(scenarios.length);
 for(const s of scenarios){
  expect(s.id).toContain(service.code);expect(s.sources.length).toBeGreaterThan(0);
  for(const ref of s.sources)expect(SCENARIO_SOURCES[ref].url).toMatch(/^https:\/\//);
  const draft:ClickReport={mode:'服務性問題',service,option:service.options?.[0]??null,category:categories[1],templateId:null,reason:s.text,supplement:''};
  const body=buildCasePayload(draft,'isolated-request');expect(body.text).toContain(service.code);expect(body.text).toContain(s.text);
 }
});
it('unknown service never receives generic fallback reasons',()=>{
 expect(getReportScenarios('服務性問題','unknown')).toEqual([]);
});
