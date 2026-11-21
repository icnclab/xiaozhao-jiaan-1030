/* Independent SOS PWA. Login token never logged; backend RBAC remains authoritative. */
(()=>{'use strict';
const BASE='/api', ROOT='/api/jiaan1030', KEY='xz_sos_private_device_session_v1';
const el=id=>document.getElementById(id);const roles={caregiver:'照服員',supervisor:'居督',director:'主任',admin:'管理員'};
const cats={fall:'跌倒',violence:'暴力',injury:'傷口',unresponsive:'昏倒／意識異常',traffic:'車禍',self_harm:'自傷風險',other:'其他／不確定'};
let token='',user=null,selection=null,busy=false,requestId=null,promptInstall=null,pollTimer=null;
const originalTitle=document.title;
const show=(id,yes)=>el(id).classList.toggle('hidden',!yes);
function toast(s){const t=el('toast');t.textContent=s;show('toast',!!s)}
function errorText(e){return e && e.message ? e.message : '連線失敗，請稍後重試'}
async function req(path,method='GET',body=null){const headers={};if(token)headers.Authorization='Bearer '+token;if(body)headers['Content-Type']='application/json';const res=await fetch(BASE+path,{method,headers,cache:'no-store',body:body?JSON.stringify(body):undefined});let data={};try{data=await res.json()}catch{} if(!res.ok){const detail=data?.error||data?.detail||{};const msg=detail?.message||(typeof detail==='string'?detail:null)||('HTTP '+res.status);const err=new Error(msg);err.status=res.status;err.code=detail?.code||null;throw err}return data}
function save(){try{if(el('remember').checked&&token)localStorage.setItem(KEY,token);else localStorage.removeItem(KEY)}catch{}}
function stopPolling(){if(pollTimer){clearInterval(pollTimer);pollTimer=null}}
async function logout(revoke=true){if(revoke&&token){try{await req('/auth/logout','POST')}catch{}}token='';user=null;stopPolling();soundedStages.clear();lastUnclaimed=[];sirenOff();el('alerts').checked=false;document.title=originalTitle;try{localStorage.removeItem(KEY)}catch{};el('password').value='';show('app',false);show('logout',false);show('login',true);toast('已登出緊急通報 APP')}
async function bootstrap(t,remembered=false){token=t;try{const u=await req('/me');if(!roles[u.role])throw new Error('此帳號沒有獨立 SOS APP 權限');user=u;show('login',false);show('app',true);show('logout',true);show('caregiver',u.role==='caregiver');show('manager',u.role!=='caregiver');show('caregiverSetup',u.role==='director'||u.role==='admin');if(u.role==='director'||u.role==='admin')await loadCaregivers();el('identity').textContent=(u.display_name||u.username)+'｜'+roles[u.role]+'｜'+(u.org?.name||'');if(!remembered)save();/* 必須在第一次 reload 前，以已驗證 user.id 恢復本帳號的聲音偏好。 */el('alerts').checked=u.role!=='caregiver'&&savedSoundPreference();await reload();stopPolling();if(u.role!=='caregiver'){pollTimer=setInterval(()=>{if(token)reload()},5000);void restoreNotificationState()}}catch(e){token='';user=null;try{localStorage.removeItem(KEY)}catch{};show('app',false);show('login',true);show('logout',false);toast('登入需要重新驗證：'+errorText(e))}}
async function login(){if(busy)return;const username=el('username').value.trim(),password=el('password').value;if(!username||!password){toast('請輸入帳號及密碼');return}/* 點登入也是使用者互動；僅預先喚醒已曾授權裝置的音訊，不為其他帳號自動勾選或播放。 */if(anySavedSoundPreference()){const ctx=ensureSiren();if(ctx&&ctx.state==='suspended')void ctx.resume().catch(()=>{audioFailed=true;updateRingStatus()})}busy=true;el('loginBtn').disabled=true;try{const r=await req('/auth/sos/login','POST',{username,password});if(r.status!=='ok'||!r.session_token)throw Error('登入未成功');el('password').value='';await bootstrap(r.session_token)}catch(e){toast('登入失敗：'+errorText(e))}finally{busy=false;el('loginBtn').disabled=false}}
function box(parent,text){const p=document.createElement('p');p.textContent=text;parent.appendChild(p)}
function button(parent,label,fn,cls=''){const b=document.createElement('button');b.type='button';b.textContent=label;if(cls)b.className=cls;b.addEventListener('click',fn);parent.appendChild(b);return b}
function formatDate(s){if(!s)return '';const d=new Date(s);return Number.isNaN(d.getTime())?s:d.toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:true})}
// 2026-11-14：卡片頂部與處理歷程全面改成一般人（含年長照護人員）容易理解的繁體中文，
// 不直接顯示 created/acknowledged/resolved/cancelled 這些技術狀態字。角色稱呼依照
// 「督導」「主任」等既有用語；只在「有真實紀錄」時才顯示處置者，沒有紀錄就說「尚無
// 處理紀錄」，不自行生成假的處理人員。
const STATUS_PHRASE={open:'等待督導接手',acknowledged:'處理中',resolved:'已處理完成',cancelled:'已取消（誤報）'};
const ROLE_LABEL={supervisor:'居督',director:'主任',admin:'管理員',caregiver:'照服員'};
function roleLabel(role){return ROLE_LABEL[role]||'人員'}
function historyLine(ev){
  const who=ev.actor_name?roleLabel(ev.actor_role)+'「'+ev.actor_name+'」':null;
  switch(ev.event_type){
    case 'created': return (who||'照服員')+'已送出緊急通報';
    case 'acknowledged': return who?who+'已接手處理':'已有人接手處理';
    case 'resolved': return who?who+'已確認處理完成並結案':'事件已處理完成';
    case 'cancelled': return who?who+'已取消此通報（確認為誤報）':'通報已取消';
    default: return who?who+'更新了這筆通報的狀態':'通報狀態已更新';
  }
}
function elapsedSeconds(iso){const n=Date.parse(iso);return Number.isFinite(n)?Math.max(0,Math.floor((Date.now()-n)/1000)):0}
function unattendedLabel(item){if(item.status!=='open')return '';const secs=elapsedSeconds(item.created_at);if(secs>=180)return '已等待超過 3 分鐘：請立即電話聯絡值班居督／主任，確認有人接手';if(secs>=60)return '已等待超過 1 分鐘：請直接電話催促接手';return ''}
function caseCard(parent,item){
  const card=document.createElement('div');card.className='case';card.setAttribute('role','group');
  const title=document.createElement('strong');title.style.fontSize='1.05rem';
  title.textContent=(cats[item.category]||'緊急通報')+'｜'+(STATUS_PHRASE[item.status]||item.status);
  card.appendChild(title);
  const meta=document.createElement('div');meta.className='meta';
  meta.textContent='建立 '+formatDate(item.created_at)+(item.acknowledged_at?' · 接手 '+formatDate(item.acknowledged_at):'');
  card.appendChild(meta);
  const late=unattendedLabel(item);if(late){const lateEl=document.createElement('div');lateEl.className='meta late';lateEl.setAttribute('role','alert');lateEl.textContent=late;card.appendChild(lateEl)}
  const actions=document.createElement('div');actions.className='row';
  if(user.role!=='caregiver'&&item.status==='open')button(actions,'接手處理',()=>change(item,'acknowledge'),'danger');
  if(user.role!=='caregiver'&&item.status==='acknowledged')button(actions,'結束通報',()=>change(item,'resolve'));
  // 「取消誤報」只在尚未接手(open)時才顯示；原通報人或督導/主任/管理員才看得到這個按鈕，
  // 但實際權限一律由後端 check_role/get_one 再驗證一次，不只靠前端隱藏按鈕。
  if(item.status==='open'&&(user.role!=='caregiver'||item.created_by===user.id))button(actions,'取消誤報',()=>change(item,'cancel'),'secondary');
  if(actions.childNodes.length)card.appendChild(actions);
  const details=document.createElement('details');
  const summary=document.createElement('summary');summary.textContent='處理進度';details.appendChild(summary);
  const inner=document.createElement('div');details.appendChild(inner);
  details.addEventListener('toggle',async()=>{
    if(!details.open||inner.dataset.loaded)return;
    try{
      const h=await req('/jiaan1030/emergencies/'+encodeURIComponent(item.id)+'/history');
      const items=h.items||[];
      if(!items.length){box(inner,'尚無處理紀錄');inner.dataset.loaded='1';return}
      items.forEach((ev,idx)=>{
        const step=document.createElement('div');step.className='step';
        const t=document.createElement('div');t.className='step-title';t.textContent='①②③④⑤⑥⑦⑧⑨'[idx]||('第'+(idx+1)+'步');
        const time=document.createElement('div');time.className='muted hint';time.textContent=formatDate(ev.created_at);
        const line=document.createElement('div');line.textContent=historyLine(ev);
        step.appendChild(t);step.appendChild(time);step.appendChild(line);inner.appendChild(step)
      });
      inner.dataset.loaded='1';
    }catch(e){box(inner,'目前無法讀取處理歷程：'+errorText(e))}
  });
  card.appendChild(details);parent.appendChild(card)
}

// XZ_SOS_AMBULANCE_SIREN_V2 - 2026/11/14 手機實測回饋：原本單振盪器＋sine LFO的連續
// warble聲太滑稽、不夠尖銳。改成雙音交替（hi-lo "yelp"）救護車警示風格：兩個常駐
// sawtooth振盪器（音色比sine更明亮刺耳，接近真實警示器），用一個square波LFO驅動兩個
// WaveShaper做出的二值開關（非平滑sine調變），讓兩個音高「切換」而不是「滑過去」，
// 聽感上明確是兩個音在交替，不是一個音在搖擺。振盪器本身永不停止（只調整gain），
// 聲音之間沒有空檔，保留原設計「不能有間斷」的要求。全部經過限幅器
// (DynamicsCompressorNode) 防止削波/爆音，且總音量上限鎖死在安全範圍內，使用者可調
// 的音量滑桿只在這個安全範圍內縮放，不會、也不宣稱能超越手機硬體音量上限、系統靜音
// 或瀏覽器自動播放限制。僅在頁面開啟、可見且位於前景時發聲；絕不代表背景或鎖定畫面
// 也會持續響鈴。「靜音」只調整本機播放音量，不呼叫任何API、不改變事件業務狀態、不等於ACK。
const soundedStages=new Map();
const MAX_SAFE_VOLUME=0.35; // 安全音量上限（0~1 內部增益），滑桿只在 0~這個值之間縮放
let sirenCtx=null,sirenOscA=null,sirenOscB=null,sirenGainA=null,sirenGainB=null,sirenLfo=null,
  shaperPos=null,shaperNeg=null,invert=null,masterGain=null,limiter=null,
  sirenActive=false,lastUnclaimed=[],userVolume=0.7,muted=false,audioFailed=false;
const SOUND_PREF='xz_sos_sound_enabled_v1';
function soundPrefKey(){return SOUND_PREF+':'+(user?.id||'anonymous')}
function savedSoundPreference(){try{return localStorage.getItem(soundPrefKey())==='1'}catch{return false}}
function anySavedSoundPreference(){try{return Object.keys(localStorage).some(k=>k.startsWith(SOUND_PREF+':')&&localStorage.getItem(k)==='1')}catch{return false}}
async function restoreAudioFromGesture(){if(!el('alerts')?.checked)return false;const ctx=ensureSiren();if(!ctx)return false;try{if(ctx.state==='suspended')await ctx.resume();audioFailed=ctx.state!=='running'}catch{audioFailed=true}updateRingStatus();evaluateSiren();return !audioFailed}
function emergencyStage(item){if(item.status!=='open')return null;const secs=elapsedSeconds(item.created_at);return secs>=180?'180s':secs>=60?'60s':'new'}
function binaryShaperCurve(invertCurve){const n=256,curve=new Float32Array(n);for(let i=0;i<n;i++){const x=i/(n-1)*2-1;const on=invertCurve?x<0:x>0;curve[i]=on?1:0}return curve}
function ensureSiren(){
  const AudioCtx=window.AudioContext||window.webkitAudioContext;
  if(!AudioCtx){audioFailed=true;return null}
  if(sirenCtx)return sirenCtx;
  try{
    sirenCtx=new AudioCtx();
    // 兩個常駐音源，分別代表救護車警示的「高音」與「低音」。
    sirenOscA=sirenCtx.createOscillator();sirenOscA.type='sawtooth';sirenOscA.frequency.value=880;
    sirenOscB=sirenCtx.createOscillator();sirenOscB.type='sawtooth';sirenOscB.frequency.value=620;
    // 一個 square LFO 驅動兩個 WaveShaper，做出「非 A 則 B」的二值切換（不是平滑漸變），
    // 聽起來是兩個音在交替，不是一個音在滑動——這是跟舊版最大的差異。
    sirenLfo=sirenCtx.createOscillator();sirenLfo.type='square';sirenLfo.frequency.value=4.2;
    shaperPos=sirenCtx.createWaveShaper();shaperPos.curve=binaryShaperCurve(false);
    shaperNeg=sirenCtx.createWaveShaper();shaperNeg.curve=binaryShaperCurve(true);
    invert=sirenCtx.createGain();invert.gain.value=1; // LFO 原始訊號也直接餵給 shaperNeg
    sirenLfo.connect(shaperPos);sirenLfo.connect(shaperNeg);
    sirenGainA=sirenCtx.createGain();sirenGainA.gain.value=0;
    sirenGainB=sirenCtx.createGain();sirenGainB.gain.value=0;
    // WaveShaper 輸出 0/1，用來「調變」各自的目標音量（透過再一層 Gain 的 gain 參數自動化無法直接拿訊號相乘，
    // 改用 ConstantSource 當作可被 AudioParam 連接的乘法輸入來源不易，這裡用較穩定的做法：
    // shaper 輸出直接接到 gainA/gainB 的 gain AudioParam，由 masterGain 統一控制總音量）。
    shaperPos.connect(sirenGainA.gain);
    shaperNeg.connect(sirenGainB.gain);
    sirenOscA.connect(sirenGainA);sirenOscB.connect(sirenGainB);
    masterGain=sirenCtx.createGain();masterGain.gain.value=0.0001;
    sirenGainA.connect(masterGain);sirenGainB.connect(masterGain);
    // 限幅器：兩個音源相加＋手機喇叭常見的小型驅動放大，容易削波爆音；這裡強制壓縮避免。
    limiter=sirenCtx.createDynamicsCompressor();
    limiter.threshold.value=-6;limiter.knee.value=2;limiter.ratio.value=16;
    limiter.attack.value=0.003;limiter.release.value=0.1;
    masterGain.connect(limiter);limiter.connect(sirenCtx.destination);
    sirenOscA.start();sirenOscB.start();sirenLfo.start();
    audioFailed=false;
  }catch(e){audioFailed=true;sirenCtx=null;return null}
  return sirenCtx;
}
function sirenStageParams(stage){return stage==='180s'?{rate:5.2,volume:1}:stage==='60s'?{rate:4.2,volume:0.85}:{rate:3.2,volume:0.7}}
function effectiveVolume(stageVolumeRatio){return muted?0:Math.max(0,Math.min(1,userVolume))*MAX_SAFE_VOLUME*stageVolumeRatio}
function sirenOn(stage){
  const ctx=ensureSiren();if(!ctx){updateRingStatus();return}
  if(ctx.state==='suspended')void ctx.resume().then(()=>{audioFailed=ctx.state!=='running';updateRingStatus()}).catch(()=>{audioFailed=true;updateRingStatus()});
  const p=sirenStageParams(stage);
  const t=ctx.currentTime;
  sirenLfo.frequency.setTargetAtTime(p.rate,t,0.25);
  masterGain.gain.cancelScheduledValues(t);
  masterGain.gain.setTargetAtTime(effectiveVolume(p.volume),t,0.08);
  sirenActive=true;
  updateRingStatus();
}
function sirenOff(){
  if(!sirenCtx){sirenActive=false;updateRingStatus();return}
  masterGain.gain.cancelScheduledValues(sirenCtx.currentTime);
  masterGain.gain.setTargetAtTime(0.0001,sirenCtx.currentTime,0.15);
  sirenActive=false;
  updateRingStatus();
}
function updateRingStatus(){
  const s=el('ringStatus');if(!s)return;
  if(!el('alerts')?.checked){s.textContent='🔈 本頁警示音尚未啟用；首次請勾選啟用。';return}
  if(audioFailed||!sirenCtx||sirenCtx.state!=='running'){s.textContent='⚠️ 聲音尚未真正啟用。請點選「試聽警示音」或重新勾選啟用；若瀏覽器阻擋，仍要看畫面並電話通知。';return}
  if(muted){s.textContent='🔇 已靜音（事件狀態不受影響，仍需用畫面確認是否有未接手通報）';return}
  s.textContent=sirenActive?'🔊 警示音播放中':'🔈 目前無未接手通報，警示音待命';
}
function evaluateSiren(){
  const alertsOn=el('alerts')&&el('alerts').checked;
  // 手機 PWA 的 document.hasFocus() 在畫面可見時也可能回傳 false；只用 visibility 判斷前景。
  const foreground=document.visibilityState==='visible';
  if(!alertsOn||!foreground){sirenOff();return}
  const active=new Set(lastUnclaimed.map(x=>x.id));
  for(const id of soundedStages.keys())if(!active.has(id))soundedStages.delete(id);
  const priorities={new:0,'60s':1,'180s':2};
  let highest=null;
  for(const item of lastUnclaimed){
    const stage=emergencyStage(item);
    if(!stage)continue;
    const previous=soundedStages.get(item.id);
    if(previous===undefined||priorities[previous]<priorities[stage]){
      soundedStages.set(item.id,stage);
      if('Notification'in window&&Notification.permission==='granted'){
        try{new Notification('小照 SOS｜緊急通報尚未接手',{body:stage==='180s'?'已超過 180 秒；立即依值班電話升級':stage==='60s'?'已超過 60 秒；請電話催促接手':'請立即確認並依流程電話聯絡',tag:'xz-sos-standalone-'+item.id+'-'+stage})}catch(_){/* 瀏覽器可能拒絕通知 */}
      }
    }
    if(highest===null||priorities[stage]>priorities[highest])highest=stage;
  }
  if(highest!==null)sirenOn(highest);else sirenOff();
}
function notifyVisibleUnclaimed(unclaimed){lastUnclaimed=unclaimed;evaluateSiren()}
function onAlertsToggle(){if(!user||user.role==='caregiver')return;try{localStorage.setItem(soundPrefKey(),el('alerts').checked?'1':'0')}catch{};if(el('alerts').checked)void restoreAudioFromGesture();else{evaluateSiren();updateRingStatus()}}
function onVolumeChange(){const v=el('sirenVolume');if(!v)return;userVolume=Math.max(0,Math.min(100,Number(v.value)||0))/100;if(sirenCtx&&sirenActive){const stage=[...soundedStages.values()].sort((a,b)=>({new:0,'60s':1,'180s':2}[b]-{new:0,'60s':1,'180s':2}[a]))[0]||'new';sirenOn(stage)}}
function onMuteToggle(){muted=!muted;const b=el('sirenMute');if(b)b.textContent=muted?'取消靜音':'靜音警示音';if(sirenCtx&&sirenActive){const stage=[...soundedStages.values()].sort((a,b)=>({new:0,'60s':1,'180s':2}[b]-{new:0,'60s':1,'180s':2}[a]))[0]||'new';sirenOn(stage)}else updateRingStatus()}
// XZ_SOS_SIREN_PREVIEW_V1：試聽不建立任何事件、不呼叫後端 API，只在使用者點擊（符合
// 瀏覽器自動播放政策的使用者手勢）時短暫播放 1.6 秒讓使用者確認音量與音色，播完自動停止。
function onSirenPreview(){
  const ctx=ensureSiren();if(!ctx){updateRingStatus();return}
  if(ctx.state==='suspended')ctx.resume().catch(()=>{audioFailed=true;updateRingStatus()});
  const t=ctx.currentTime;
  sirenLfo.frequency.setTargetAtTime(4.2,t,0.05);
  masterGain.gain.cancelScheduledValues(t);
  masterGain.gain.setTargetAtTime(effectiveVolume(0.85),t,0.05);
  sirenActive=true;updateRingStatus();
  setTimeout(()=>{if(!lastUnclaimed.some(x=>emergencyStage(x)))sirenOff()},1600);
}
document.addEventListener('visibilitychange',evaluateSiren);
window.addEventListener('blur',evaluateSiren);
window.addEventListener('focus',evaluateSiren);

async function reload(){if(!token)return;try{const a=await req('/jiaan1030/emergencies?status=active');const all=a.items||[];if(user.role==='caregiver'){const target=el('myCases');target.replaceChildren();if(!all.length)box(target,'目前沒有進行中的通報');all.forEach(e=>caseCard(target,e))}else{const open=all.filter(x=>x.status==='open'),ack=all.filter(x=>x.status==='acknowledged');el('openCount').textContent=open.length;el('ackCount').textContent=ack.length;document.title=open.length?('【'+open.length+'筆未接手】'+originalTitle):originalTitle;notifyVisibleUnclaimed(open);for(const [id,items] of [['openCases',open],['ackCases',ack]]){const target=el(id);target.replaceChildren();if(!items.length)box(target,'目前沒有案件');items.forEach(x=>caseCard(target,x))}const resolved=await req('/jiaan1030/emergencies?status=resolved');const target=el('resolvedCases');target.replaceChildren();(resolved.items||[]).slice(0,20).forEach(x=>caseCard(target,x))}toast('資料已更新')}catch(e){if(e.status===401){await logout(false)}else toast('無法更新通報：'+errorText(e))}}
// 2026-11-14：結束通報、取消誤報都要二次確認；取消誤報一定要填原因，結束通報的原因
// 是建議填寫（非必填，避免改變既有「立即結案」的使用習慣）。原因只會送到伺服器做
// 處理摘要與稽核紀錄，請提醒使用者不要輸入個案細節。
async function change(item,verb){
  const labels={acknowledge:'接手處理',resolve:'結束通報',cancel:'取消誤報'};
  const confirmMsg={acknowledge:'確定由你接手這筆緊急通報？',resolve:'你已確認事件實際處理完成，確定結束這筆通報？',cancel:'確定這筆通報是誤報，要取消嗎？取消後不能復原，需要的話要重新建立新的通報。'}[verb];
  if(!confirm(confirmMsg))return;
  let reason=null;
  if(verb==='cancel'){
    reason=(prompt('請簡短說明取消原因（必填，請勿輸入個案個資）：')||'').trim();
    if(!reason){toast('已取消操作：取消誤報需要填寫原因');return}
  }else if(verb==='resolve'){
    reason=(prompt('可簡短說明處理摘要（選填，請勿輸入個案個資，直接按確定可略過）：')||'').trim()||null;
  }
  const id=crypto.randomUUID();
  const body=verb==='cancel'?{client_request_id:id,reason}:{client_request_id:id,...(reason?{reason}:{})};
  try{
    await req('/jiaan1030/emergencies/'+encodeURIComponent(item.id)+'/'+verb,'POST',body);
    toast('已'+labels[verb]);await reload()
  }catch(e){toast('操作失敗：'+errorText(e));await reload()}
}
async function send(){if(busy||!selection)return;if(!confirm('再次確認：送出「'+cats[selection]+'」緊急通報？'))return;busy=true;el('send').disabled=true;requestId=requestId||crypto.randomUUID();try{await req('/jiaan1030/emergencies','POST',{category:selection,client_request_id:requestId});toast('通報已建立，但通知送達仍須獨立確認；危急請立即電話求援');requestId=null;selection=null;show('confirm',false);await reload()}catch(e){toast('通報結果未確認：'+errorText(e)+'。不要立刻重複送出，先更新事件清單。')}finally{busy=false;el('send').disabled=false}}
function urlBase64ToUint8Array(base64){const padding='='.repeat((4-base64.length%4)%4);const raw=atob((base64+padding).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from([...raw].map(c=>c.charCodeAt(0)))}
// 確認本機 PushSubscription 的應用伺服器公鑰符合目前環境，避免金鑰輪替後假稱已恢復。
function pushKeyMatches(sub,serverPublicKey){
  const browserKey=sub?.options?.applicationServerKey;
  if(!browserKey||!serverPublicKey)return null;
  const got=new Uint8Array(browserKey),expected=urlBase64ToUint8Array(serverPublicKey);
  return got.length===expected.length&&got.every((v,i)=>v===expected[i]);
}

// XZ_SOS_SW_ACTIVATION_WAIT_V1: do not subscribe before the worker is active.
async function waitForSosWorker(reg){
  const scope='/api/jiaan1030/sos-app/';
  if(!reg.scope.endsWith(scope))throw Error('SOS Service Worker 範圍不正確');
  const workerReady=()=>reg.active && reg.active.state==='activated';
  if(workerReady())return reg;
  const deadline=Date.now()+15000;
  while(Date.now()<deadline){
    if(workerReady())return reg;
    const current=reg.installing||reg.waiting||reg.active;
    if(current && current.state==='redundant')throw Error('SOS Service Worker 安裝失敗，請重新整理');
    await new Promise(resolve=>setTimeout(resolve,200));
  }
  throw Error('SOS Service Worker 啟用逾時；請重新整理後再啟用通知');
}

// 2026-11-13: 區分清楚的狀態文字，不把「公鑰缺失」「使用者拒絕」「帳號衝突」混為一句泛用錯誤。
function describePushSetupError(e){
  if(e.code==='subscription_owned_by_other_user')
    return{state:'conflict',text:'此瀏覽器的通知目前屬於同機構其他帳號。請按「啟用此裝置通知」並確認換綁；系統不會跨機構接管。'};
  if(e.message==='MISSING_PUBLIC_KEY')
    return{state:'config_error',text:'系統設定尚未完成（缺少 Web Push 公鑰），這不是你的帳號或授權問題，請聯絡管理者確認伺服器設定。'};
  if(e.message==='PERMISSION_DENIED')
    return{state:'denied',text:'瀏覽器已封鎖此裝置的通知。請到手機或瀏覽器的網站設定中，針對本網站重新允許通知後再試一次（我們不會重複彈出要求）。'};
  if(e.message==='UNSUPPORTED')
    return{state:'unsupported',text:'此瀏覽器不支援背景推播。仍可使用頁面開啟時的前景提醒與聲音，只是不會有離開頁面後的通知。'};
  return{state:'error',text:errorText(e)};
}

async function notifyEnable(){try{
  if(!('serviceWorker'in navigator)||!('PushManager'in window)||!('Notification'in window))throw Error('UNSUPPORTED');
  const permission=await Notification.requestPermission();
  if(permission!=='granted')throw Error(permission==='denied'?'PERMISSION_DENIED':'尚未允許通知');
  const config=await req('/jiaan1030/webpush/config');
  if(!config.public_key)throw Error('MISSING_PUBLIC_KEY');
  const reg=await navigator.serviceWorker.register('/api/jiaan1030/sos-app/sw.js',{scope:'/api/jiaan1030/sos-app/'});
  const activeReg=await waitForSosWorker(reg);
  let sub=await activeReg.pushManager.getSubscription();
  if(sub&&pushKeyMatches(sub,config.public_key)===false){
    if(!confirm('此瀏覽器訂閱使用舊版推播公鑰，需要重新訂閱才能接收新通知。是否更新本機訂閱？'))return;
    if(!(await sub.unsubscribe()))throw Error('無法移除舊訂閱；請在瀏覽器網站設定中重設通知後重試');
    sub=null;
  }
  if(!sub)sub=await activeReg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:urlBase64ToUint8Array(config.public_key)});
  const data=sub.toJSON();
  if(!data.keys?.p256dh||!data.keys?.auth)throw Error('瀏覽器未提供完整裝置訂閱資料，請移除網站通知權限後重試');
  const payload={endpoint:data.endpoint,p256dh:data.keys.p256dh,auth:data.keys.auth};
  try{await req('/jiaan1030/webpush/subscription','POST',payload)}catch(e){
    if(e.code!=='subscription_owned_by_other_user')throw e;
    if(!confirm('這個瀏覽器目前綁定同機構的另一個帳號。確認改由目前登入帳號接收此裝置通知？'))throw e;
    await req('/jiaan1030/webpush/subscription','POST',{...payload,replace_existing:true});
  }
  el('pushState').textContent=(config.enabled?'此裝置已安全綁定目前帳號；伺服器自動派送：已開啟（仍須送達驗證）':'此裝置已安全綁定目前帳號；推播派送停用，僅供測試（不代表通知已可送達）');
  toast('已完成此裝置通知設定')
}catch(e){
  const d=describePushSetupError(e);
  el('pushState').textContent=d.text;
  toast('通知設定失敗：'+d.text)
}}

// 2026-11-13: 登入後靜默嘗試恢復既有訂閱，不重新要求授權、不重新彈出提示。
// 只有「已授權且瀏覽器本機已有訂閱」時才會靜默同步；其餘情況維持既有
// 「啟用此裝置通知」按鈕讓使用者主動操作，不偷偷繞過瀏覽器授權限制。
async function restoreNotificationState(){
  const stateEl=el('pushState'),sessionUserId=user?.id;
  if(!sessionUserId)return;
  const sameUser=()=>user?.id===sessionUserId&&Boolean(token);
  if(!('serviceWorker'in navigator)||!('PushManager'in window)||!('Notification'in window)){
    stateEl.textContent='此瀏覽器不支援背景推播；仍可使用頁面開啟時的前景提醒。';return;
  }
  if(Notification.permission==='denied'){
    stateEl.textContent='瀏覽器已封鎖此裝置的通知。請到手機或瀏覽器的網站設定中重新允許後，再按「啟用此裝置通知」。';return;
  }
  if(Notification.permission!=='granted'){
    stateEl.textContent='尚未啟用此裝置通知，請按下方按鈕開啟（只需設定一次）。';return;
  }
  // 已授權：檢查瀏覽器本機是否已有訂閱，有就靜默回報伺服器刷新，不需使用者再次點擊。
  try{
    const reg=await navigator.serviceWorker.getRegistration('/api/jiaan1030/sos-app/');
    const sub=reg?await reg.pushManager.getSubscription():null;
    if(!sub){stateEl.textContent='已允許通知，但這個瀏覽器還沒有建立訂閱，請按下方按鈕完成一次性設定。';return}
    const config=await req('/jiaan1030/webpush/config');
    if(!sameUser())return;
    if(!config.public_key){stateEl.textContent='系統設定尚未完成（缺少 Web Push 公鑰），請聯絡管理者。';return}
    if(pushKeyMatches(sub,config.public_key)===false){stateEl.textContent='本機訂閱的推播公鑰已過期；請按「啟用此裝置通知」並確認更新。尚未恢復遠端推播。';return}
    const data=sub.toJSON();
    if(!data.keys?.p256dh||!data.keys?.auth){stateEl.textContent='已允許通知，但瀏覽器訂閱資料不完整，請按下方按鈕修復一次。';return}
    if(!sameUser())return;
    await req('/jiaan1030/webpush/subscription','POST',{endpoint:data.endpoint,p256dh:data.keys.p256dh,auth:data.keys.auth});
    if(!sameUser())return;
    stateEl.textContent=(config.enabled?'此裝置通知已自動恢復有效；伺服器自動派送：已開啟（仍須送達驗證）':'此裝置通知已自動恢復有效；推播派送停用，僅供測試（不代表通知已可送達）');
  }catch(e){
    if(!sameUser())return;
    const d=describePushSetupError(e);
    stateEl.textContent=d.state==='conflict'?d.text:'已允許通知，但自動確認時發生問題（'+d.text+'），請按下方「啟用此裝置通知」按鈕重試一次。';
  }
}

async function notifyRemoteTest(){
  try{
    const config=await req('/jiaan1030/webpush/config');
    if(!config.enabled)throw Object.assign(Error('正式遠端派送目前為 OFF；不能執行真正送達測試。請先使用不發送的權限與訂閱診斷。'),{code:'dispatch_disabled'});
    if(!confirm('只對你目前登入帳號的這台裝置發送一則非緊急遠端測試通知，確定？'))return;
    const registration=await navigator.serviceWorker.getRegistration('/api/jiaan1030/sos-app/');
    if(!registration)throw Error('請先啟用此裝置通知');
    const subscription=await registration.pushManager.getSubscription();
    if(!subscription)throw Error('請先啟用此裝置通知');
    const result=await req('/jiaan1030/webpush/self-test','POST',{endpoint:subscription.endpoint});
    toast(result.status==='provider_accepted'?'伺服器已向推播服務提交測試；請查看這台裝置是否真正收到。':'測試結果未確認');
  }catch(e){
    const msg=e.code==='self_test_disabled'?'此環境目前停用遠端推播測試（這是刻意的設定，不是故障或帳號問題）。'
      :e.status===404?'目前伺服器版本沒有可用的本人裝置測試路由，沒有假裝成功；請由管理員確認正式 SOS 版本。'
      :errorText(e);
    toast('遠端測試失敗：'+msg)
  }
}

async function diagnosePush(){const parts=[];parts.push('通知API：'+(('Notification'in window)?'支援':'不支援'));parts.push('權限：'+(('Notification'in window)?Notification.permission:'無'));parts.push('Service Worker：'+(('serviceWorker'in navigator)?'支援':'不支援'));try{const reg=await navigator.serviceWorker.getRegistration('/api/jiaan1030/sos-app/');const sub=reg?await reg.pushManager.getSubscription():null;const cfg=await req('/jiaan1030/webpush/config');parts.push('Worker：'+(reg?.active?'已啟用':'未啟用'));parts.push('訂閱：'+(sub?'存在':'不存在'));parts.push('VAPID：'+(!cfg.public_key?'缺失':!sub?'公鑰已提供（未訂閱）':pushKeyMatches(sub,cfg.public_key)===false?'⚠️ 與本機訂閱不一致':pushKeyMatches(sub,cfg.public_key)===true?'與本機訂閱相符':'有公鑰，瀏覽器無法比對'));parts.push('正式派送：'+(cfg.enabled?'ON':'OFF'))}catch(e){parts.push('後端診斷：'+errorText(e))}el('pushState').textContent=parts.join('｜')+'。這是本機診斷，沒有發送通知，也不代表實際送達。'}

async function notifyTest(){try{if(Notification.permission!=='granted')throw Error('先允許通知');const reg=await navigator.serviceWorker.register('/api/jiaan1030/sos-app/sw.js',{scope:'/api/jiaan1030/sos-app/'});const activeReg=await waitForSosWorker(reg);await activeReg.showNotification('小照｜本機顯示測試',{body:'這不是緊急事件，沒有傳送到伺服器',tag:'xz-sos-local-test'});toast('本機顯示測試已送出；這不是遠端推播驗證')}catch(e){toast(errorText(e))}}
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();promptInstall=e});el('loginBtn').addEventListener('click',login);el('password').addEventListener('keydown',e=>{if(e.key==='Enter')login()});el('logout').addEventListener('click',()=>logout(true));el('refresh').addEventListener('click',reload);el('install').addEventListener('click',async()=>{show('installHelp',true);if(promptInstall){await promptInstall.prompt();promptInstall=null}});el('categories').addEventListener('click',e=>{const btn=e.target.closest('button[data-cat]');if(!btn)return;selection=btn.dataset.cat;requestId=null;el('selected').textContent=cats[selection];show('confirm',true);el('confirm').scrollIntoView({behavior:'smooth'})});el('cancel').addEventListener('click',()=>show('confirm',false));el('send').addEventListener('click',send);el('pushEnable').addEventListener('click',notifyEnable);if(el('alerts'))el('alerts').addEventListener('change',onAlertsToggle);if(el('sirenVolume'))el('sirenVolume').addEventListener('input',onVolumeChange);if(el('sirenMute'))el('sirenMute').addEventListener('click',onMuteToggle);if(el('sirenPreview'))el('sirenPreview').addEventListener('click',onSirenPreview);async function loadCaregivers(){try{const users=await req('/admin/users');const sel=el('cgSelect');sel.replaceChildren();for(const u of users){if(u.role!=='caregiver'||!u.is_active||u.is_deleted)continue;const o=document.createElement('option');o.value=u.id;o.textContent=u.username+' · '+u.display_name;sel.appendChild(o)}if(!sel.options.length)toast('本機構沒有可設定密碼的在職照服員');updateCgSelection()}catch(e){toast('載入照服員清單失敗：'+errorText(e))}}
const weakPasswords=new Set(['123456','12345678','password','qwerty','111111','000000']);function passwordProblem(pwd){if(pwd.length<6)return'至少需要 6 字元';if(weakPasswords.has(pwd.toLowerCase())||/^(.)\1+$/.test(pwd))return'這是常見弱密碼，請改用其他密碼';return''}function updateCgSelection(){const s=el('cgSelect');el('cgSelected').textContent=s.selectedOptions[0]?'已選擇：'+s.selectedOptions[0].textContent:'尚未選擇照服員'}function updatePasswordHint(){const p=passwordProblem(el('cgPassword').value);el('cgPasswordHint').textContent=p||'格式符合要求；儲存前仍會再次確認。'}
async function setCgPassword(){const target=el('cgSelect').value,pwd=el('cgPassword').value,problem=passwordProblem(pwd);if(!target||problem){toast(!target?'請先選擇照服員':problem);return}const selected=el('cgSelect').selectedOptions[0]?.textContent||'選取的照服員';if(!confirm('確認為「'+selected+'」設定新的 SOS 密碼？舊 SOS 工作階段將需要重新登入。'))return;const btn=el('cgSetPassword');btn.disabled=true;try{await req('/admin/users/'+encodeURIComponent(target)+'/sos-password','POST',{password:pwd});toast('已設定 SOS 登入密碼');el('cgPassword').value='';updatePasswordHint()}catch(e){toast('設定失敗：'+errorText(e))}finally{btn.disabled=false}}
el('pushTest').addEventListener('click',notifyTest);el('pushRemoteTest').addEventListener('click',notifyRemoteTest);const diag=document.createElement('button');diag.type='button';diag.className='secondary';diag.textContent='檢查權限與訂閱（不發送）';diag.addEventListener('click',diagnosePush);el('pushRemoteTest').before(diag);el('cgSetPassword').addEventListener('click',setCgPassword);el('cgSelect').addEventListener('change',updateCgSelection);el('cgPassword').addEventListener('input',updatePasswordHint);el('cgTogglePassword').addEventListener('click',()=>{const p=el('cgPassword');p.type=p.type==='password'?'text':'password';el('cgTogglePassword').textContent=p.type==='password'?'顯示':'隱藏'});
// 不用『任一帳號曾勾選』決定目前帳號的聲音開關；bootstrap 已依已驗證 user.id 恢復。
(async()=>{let saved='';try{saved=localStorage.getItem(KEY)||''}catch{}if(saved){el('remember').checked=true;await bootstrap(saved,true)}})();
})();
