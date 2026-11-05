import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { api, errorMessage, newRequestId, post, type Category, type CaseDetail } from '../../api';
import { REPORT_SERVICES, type ReportService } from '../reportServices';
import { buildCasePayload, buildEmergencyPayload, isCreatedCase, reportText, type CasePayload, type ClickReport } from '../reportSubmission';
import { REPORT_MODES, getReportScenarios, resolveReceivingCategory, SCENARIO_SOURCES, type ReportMode } from '../reportScenarios';

type Stage = 'entry' | 'services' | 'options' | 'details' | 'preview';
const PAGE_SIZE = 8;

export function ReportPreviewPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const preset = location.state as { transcript_id?: string; summary?: string } | null;
  const [stage, setStage] = useState<Stage>('entry');
  const [mode, setMode] = useState<ReportMode | null>(null);
  const [service, setService] = useState<ReportService | null>(null);
  const [option, setOption] = useState<{code: string; name: string} | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [text, setText] = useState(preset?.summary ?? '');
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CaseDetail | null>(null);
  const [servicePage, setServicePage] = useState(0);
  const [markEmergency, setMarkEmergency] = useState(false);
  const [emergencyStatus, setEmergencyStatus] = useState<'idle' | 'sent' | 'error'>('idle');
  const [emergencyErrorMsg, setEmergencyErrorMsg] = useState<string | null>(null);
  const stepRef = useRef<HTMLParagraphElement>(null);
  const pending = useRef(false);
  const requestId = useRef(newRequestId());
  const emergencyRequestId = useRef(newRequestId());
  const submitted = useRef<CasePayload | null>(null);
  const locked = busy || !!submitted.current;
  const isSafetyMode = mode === '人身安全事件';
  const loadCategories = () => {
    setLoadError(null); setCategories(null);
    api<Category[]>('/api/categories').then(setCategories).catch(setLoadError);
  };
  useEffect(loadCategories, []);
  useEffect(() => {
    stepRef.current?.focus({preventScroll:true});
    stepRef.current?.scrollIntoView?.({block:'start'});
  }, [stage, servicePage]);
  const category = resolveReceivingCategory(mode,categories);
  const scenarios = getReportScenarios(mode,service?.code);
  const selectedScenario = scenarios.find(s=>s.text===reason);
  const draft: ClickReport = {mode,service,option,category,templateId:null,reason,supplement:text};
  const complete = !!mode && !!category && !!selectedScenario && reportText(draft).length <= 1000;
  const clearReason = () => { setReason(null); setError(null); setMarkEmergency(false); setEmergencyStatus('idle'); setEmergencyErrorMsg(null); };
  const restart = () => {
    if (locked) return;
    setMode(null); setService(null); setOption(null); setServicePage(0); clearReason(); setStage('entry');
  };
  const back = () => {
    if (locked) return;
    if (stage === 'preview') setStage('details');
    else if (stage === 'details') setStage(mode === '服務性問題' ? (service?.options ? 'options' : 'services') : 'entry');
    else if (stage === 'options') setStage('services');
    else setStage('entry');
  };
  const submit = async () => {
    if (pending.current || result) return;
    pending.current = true; setBusy(true); setError(null);
    try {
      const payload = submitted.current ?? buildCasePayload(draft, requestId.current, preset?.transcript_id);
      submitted.current = payload;
      const created = await post<CaseDetail>('/api/cases', payload);
      if (!isCreatedCase(created)) throw new Error('invalid case response');
      setResult(created);
      if (isSafetyMode && markEmergency) {
        try {
          const emergencyPayload = buildEmergencyPayload(reason, emergencyRequestId.current);
          await post('/api/jiaan1030/emergencies', emergencyPayload);
          setEmergencyStatus('sent');
        } catch (ee) {
          setEmergencyStatus('error');
          setEmergencyErrorMsg(`案件已建立，但緊急通報未能確認送出：${errorMessage(ee)}。請立即改用機構既有方式（電話／當面）通知督導，不要只依賴本頁通報。`);
        }
      }
    } catch (e) {
      setError(`未能確認送出結果：${errorMessage(e)}。請先查看我的案件；若需重試，留在本頁按「重試送出」，會使用原內容與相同識別碼。`);
    } finally { pending.current = false; setBusy(false); }
  };
  if (result) return <main className="page stack report-prototype">
    <h1>回報結果</h1>
    <div className="notice ok" role="status"><strong>案件已建立</strong>（案件 {result.number}，{result.status_label}）。
      {result.assignee ? `負責督導：${result.assignee.display_name}` : '尚未指派督導，請居督取消「只看指派給我」後，在待處理案件查看。'}</div>
    <p>案件建立不代表督導已讀取或回覆，也不等於已完成機構正式通報程序。</p>
    {isSafetyMode && markEmergency && emergencyStatus==='sent' && <div className="notice ok" role="status">已同時送出人身安全事件通知（僅網頁主動開啟時顯示，非背景推播；危急請同時聯絡119／110）。</div>}
    {isSafetyMode && markEmergency && emergencyStatus==='error' && <div className="notice danger" role="alert">{emergencyErrorMsg}</div>}
    <Link className="btn primary block big" to={`/liff/cases/${result.id}`}>查看案件</Link>
    <button className="btn block" onClick={() => {
      submitted.current=null; requestId.current=newRequestId(); emergencyRequestId.current=newRequestId();
      setResult(null); setMode(null); setService(null);
      setOption(null); setText(''); setReason(null); setError(null); setServicePage(0); setStage('entry');
      setMarkEmergency(false); setEmergencyStatus('idle'); setEmergencyErrorMsg(null);
    }}>再回報一件</button>
    <Link className="btn block" to="/liff/report/entry">返回問題分類</Link>
  </main>;
  const step = stage === 'entry' ? 1 : stage === 'services' || stage === 'options' ? 2 : stage === 'details' ? 3 : 4;
  return <main className="page stack report-prototype">
    <h1>點選分類回報</h1>
    <p className="report-steps" ref={stepRef} tabIndex={-1} role="status">第 {step}／4 步：{['選擇問題類型','選擇服務項目','選擇回報原因','確認並送出'][step-1]}</p>
    <p>點選即可回報，補充說明可不填。</p>
    <p className="notice warn">緊急或有人身安全風險時，請立即依機構通報流程聯絡居督及必要救援，不要等待本頁回報。</p>
    {preset?.transcript_id && <p className="notice info">送出時將附上已確認的談話摘要。</p>}
    {mode && <nav className="prototype-path" aria-label="目前選擇">{mode}{service ? ` ／ ${service.code} ${service.name}` : ''}{option ? ` ／ ${option.name}` : ''}</nav>}
    {stage === 'entry' && <section className="stack" aria-label="問題類型"><h2>想回報哪一類問題？</h2>
      {REPORT_MODES.map(m => <button className="btn block big" key={m} onClick={() => {
        if (m !== mode) {setService(null); setOption(null); clearReason();}
        setMode(m); setStage(m === '服務性問題' ? 'services' : 'details');
      }}>{m}</button>)}
    </section>}
    {stage === 'services' && <section className="stack" aria-label="服務項目"><h2>選擇服務項目</h2>
      <p>每頁最多 {PAGE_SIZE} 項，可用下一頁繼續選擇。</p>
      <div className="prototype-services">{REPORT_SERVICES.slice(servicePage*PAGE_SIZE,(servicePage+1)*PAGE_SIZE).map(s => <button className="btn block big" aria-pressed={service?.code===s.code} key={s.code} onClick={() => {
        if (s.code !== service?.code) {setOption(null); clearReason();}
        setService(s); setStage(s.options ? 'options' : 'details');
      }}><strong>{s.code}</strong><span>{s.name}</span></button>)}</div>
      <nav className="row prototype-pagination" aria-label="服務項目分頁">
        <button className="btn" disabled={servicePage===0} onClick={() => setServicePage(p=>p-1)}>上一頁</button>
        <span>第 {servicePage+1}／{Math.ceil(REPORT_SERVICES.length/PAGE_SIZE)} 頁</span>
        <button className="btn" disabled={(servicePage+1)*PAGE_SIZE>=REPORT_SERVICES.length} onClick={() => setServicePage(p=>p+1)}>下一頁</button>
      </nav>
    </section>}
    {stage === 'options' && service && <section className="stack" aria-label="服務細項"><h2>選擇服務細項</h2>
      {service.options?.map(o=><button className="btn block big" aria-pressed={option?.code===o.code} key={o.code} onClick={()=>{
        if(o.code!==option?.code) clearReason(); setOption(o); setStage('details');
      }}>{o.code} {o.name}</button>)}
    </section>}
    {stage === 'details' && mode && <section className="stack" aria-label="回報原因"><h2>{mode === '服務性問題' ? `${service?.code} 服務遇到什麼情況？` : mode === '額外要求' ? '遇到哪一種額外要求？' : '想反映哪一種問題？'}</h2>
      <p>請點選一項情境。選項依參考文獻整理，實際處理由居督依機構規範確認。</p>
      {categories===null && !loadError && <p role="status">收件資料載入中…</p>}
      {!!loadError && <div className="notice danger" role="alert">{(loadError as {status?:number}).status===401 ? '登入已失效，請重新登入。' : (loadError as {status?:number}).status===403 ? '權限不足，請聯絡機構督導。' : '收件資料載入失敗，請重試。'}<button className="btn block" onClick={loadCategories}>重新載入</button></div>}
      {categories!==null && !category && <div className="notice warn" role="alert">找不到此問題類型的既有收件分類，暫時無法送出，請聯絡居督確認。<Link to="/liff/report" state={preset}>使用原有分類回報</Link></div>}
      {scenarios.map(s=><button className={`btn block big ${reason===s.text?'primary':''}`} aria-pressed={reason===s.text} key={s.id} onClick={()=>{
        if(s.text!==reason){setMarkEmergency(false); setEmergencyStatus('idle'); setEmergencyErrorMsg(null);}
        setReason(s.text);
      }}>{s.text}</button>)}
      {mode==='申訴處理' && <p className="notice info">本頁將反映內容送交居督，不代表完成機構正式申訴或法定通報。若需迴避被反映人員，請另循機構申訴管道。</p>}
      {selectedScenario && <details className="card"><summary>情境參考來源</summary>{selectedScenario.sources.map(id=><p key={id}><a href={SCENARIO_SOURCES[id].url} target="_blank" rel="noreferrer">{SCENARIO_SOURCES[id].title}</a>：{SCENARIO_SOURCES[id].locator}</p>)}</details>}
      {isSafetyMode && selectedScenario && <section className="card stack" aria-label="緊急通報選項">
        <label><input type="checkbox" checked={markEmergency} onChange={e=>setMarkEmergency(e.target.checked)} /> 同時標記為緊急，通知督導即時查看</label>
        <p className="notice warn">僅在督導主動開啟網頁時顯示，不是背景推播或鎖屏持續響鈴；有立即危險請同時聯絡119／110及現場安全。</p>
      </section>}
      <label htmlFor="report-supplement">補充說明（選填，不用打字也能送出）</label>
      <textarea id="report-supplement" value={text} maxLength={1000} onChange={e=>setText(e.target.value)} placeholder="如需補充，請用「個案」「家屬」代稱，勿填姓名或案號" />
      {reportText(draft).length>1000 && <p className="notice danger" role="alert">內容超過長度限制，請縮短補充說明。</p>}
      <button className="btn primary block big" disabled={!complete} onClick={()=>setStage('preview')}>下一步：確認內容</button>
    </section>}
    {stage === 'preview' && <section className="card stack" aria-label="確認回報內容"><h2>確認回報內容</h2>
      <p>問題類型：{mode}</p>
      <p>回報情境：{reason}</p>
      {mode==='申訴處理' && category?.name==='其他' && <p className="notice info">將沿用「其他」既有居督收件流程，不代表正式申訴已受理。</p>}
      <p className="prototype-description">{reportText(draft)}</p>
      {!text.trim() && <p>未填補充說明，可直接送出。</p>}
      {isSafetyMode && <p>{markEmergency ? '將同時標記為緊急，通知督導即時查看。' : '未標記為緊急，僅建立一般案件。如有立即危險，請先聯絡119／110及現場安全，不要只依賴本頁。'}</p>}
      <p>按下送出後才會建立案件，讓本機構居督查看。</p>
      {error && <div className="notice danger" role="alert">{error}<Link to="/liff/cases">查看我的案件</Link></div>}
      <button className="btn primary block big" disabled={busy || !complete} onClick={submit}>{busy?'送出中…':submitted.current?'重試送出':'確認送出回報'}</button>
    </section>}
    {stage!=='entry' && <div className="row"><button className="btn" disabled={locked} onClick={back}>{stage==='preview'?'返回修改':'上一步'}</button><button className="btn" disabled={locked} onClick={restart}>重新選擇問題類型</button></div>}
    <button className="btn block" disabled={busy} onClick={()=>navigate('/liff/report/entry',{state:preset})}>返回問題分類</button>
    <p className="small muted">未送出的資料只保留在本頁，重新整理會清除。送出結果不明時，請先查看我的案件。</p>
  </main>;
}
