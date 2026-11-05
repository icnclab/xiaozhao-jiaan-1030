"use strict";
const el=id=>document.getElementById(id);
const sessionKey='xz_alert_app_session';
let token=sessionStorage.getItem(sessionKey), user=null, reg=null, timer=null;
function status(id,text){el(id).textContent=text;}
function errorMessage(data,code){return data?.error?.message||data?.detail?.message||(typeof data?.detail==='string'?data.detail:null)||`HTTP ${code}`;}
async function api(path,init={}){
 const headers={'Accept':'application/json',...(init.body?{'Content-Type':'application/json'}:{})};
 if(token)headers.Authorization=`Bearer ${token}`;
 const res=await fetch(path,{...init,headers,cache:'no-store',credentials:'same-origin'});
 const data=await res.json().catch(()=>({}));if(!res.ok)throw Error(errorMessage(data,res.status));return data;
}
function keyBytes(s){const str=atob((s+'='.repeat((4-s.length%4)%4)).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from(str,c=>c.charCodeAt(0));}
async function initSW(){if(!isSecureContext||!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window))throw Error('裝置或瀏覽器不支援安全背景推播');
 reg=await navigator.serviceWorker.register('/api/jiaan1030/alert-sw.js',{scope:'/api/jiaan1030/'});return reg;}
async function readConfig(){
 try{await initSW();const cfg=await api('/api/jiaan1030/webpush/config');
 if(!cfg.public_key){status('readiness','尚未設定 VAPID 公開金鑰，無法訂閱。');return;}
 status('readiness',cfg.enabled?'已配置推播，可由本人選擇訂閱；不保證送達。':'目前正式推播派送關閉。可以先完成本機訂閱，但不會實際送出緊急訊息。');
 el('enableButton').disabled=false;el('disableButton').disabled=false;
 }catch(e){status('readiness','目前無法啟用：'+e.message);}
}
async function subscribe(){try{status('result','正在取得通知權限…');if(!reg)await initSW();
 const cfg=await api('/api/jiaan1030/webpush/config');if(!cfg.public_key)throw Error('缺少 VAPID 公開金鑰');
 const permission=await Notification.requestPermission();if(permission!=='granted')throw Error('未授予通知權限');
 let sub=await reg.pushManager.getSubscription();if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:keyBytes(cfg.public_key)});
 const keys=sub.toJSON().keys||{};if(!keys.p256dh||!keys.auth)throw Error('瀏覽器未傳回有效金鑰');
 await api('/api/jiaan1030/webpush/subscription',{method:'POST',body:JSON.stringify({endpoint:sub.endpoint,p256dh:keys.p256dh,auth:keys.auth})});
 status('result',cfg.enabled?'已訂閱本機通知；需另做受控送達測試。':'裝置已完成訂閱，但後端派送目前關閉。');await showDeviceFingerprint();
 }catch(e){status('result','訂閱未完成：'+e.message);}}
async function unsubscribe(){try{if(!reg)await initSW();const sub=await reg.pushManager.getSubscription();if(sub){const keys=sub.toJSON().keys||{};
 await api('/api/jiaan1030/webpush/subscription',{method:'DELETE',body:JSON.stringify({endpoint:sub.endpoint,p256dh:keys.p256dh||'0000000000000000000000000000000000000000',auth:keys.auth||'00000000'})});
 await sub.unsubscribe();}status('result','已停用本機訂閱。');await showDeviceFingerprint();}catch(e){status('result','停用失敗：'+e.message);}}
async function refresh(){if(!user)return;try{const data=await api('/api/jiaan1030/emergencies?status=active');let entries=Array.isArray(data.items)?data.items:[];
 entries=entries.filter(x=>x.status==='open');const container=el('incidents');container.replaceChildren();
 if(!entries.length){container.textContent='目前沒有尚未接手通報。';return;}
 for(const x of entries){const d=document.createElement('div');d.className='case';const id=String(x.id||'').slice(0,8).toUpperCase();d.textContent=`緊急通報 #${id}｜${new Date(x.created_at).toLocaleString('zh-TW')}｜待接手`;container.appendChild(d);}
 }catch(e){status('incidents','讀取通報失敗：'+e.message);}}
async function connect(){try{user=await api('/api/me');if(!['supervisor','director','admin'].includes(user.role))throw Error('僅督導、主任、管理員可使用');
 status('identity',`已登入：${user.display_name}（${user.role}）`);el('loginSection').classList.add('hidden');el('accountSection').classList.remove('hidden');el('incidentsSection').classList.remove('hidden');
 await readConfig();await showDeviceFingerprint();await refresh();if(timer)clearInterval(timer);timer=setInterval(()=>{if(!document.hidden)refresh();},5000);
 }catch(e){user=null;el('loginSection').classList.remove('hidden');el('accountSection').classList.add('hidden');el('incidentsSection').classList.add('hidden');status('loginStatus','登入未完成：'+e.message);}}
el('loginButton').addEventListener('click',async()=>{try{const result=await api('/api/auth/login',{method:'POST',body:JSON.stringify({username:el('username').value,password:el('password').value})});
 if(!result.session_token)throw Error('沒有取得登入憑證');token=result.session_token;sessionStorage.setItem(sessionKey,token);el('password').value='';await connect();}catch(e){status('loginStatus','登入失敗：'+e.message);}});
el('enableButton').addEventListener('click',subscribe);
el('disableButton').addEventListener('click',unsubscribe);
el('logoutButton').addEventListener('click',()=>{token=null;user=null;sessionStorage.removeItem(sessionKey);if(timer)clearInterval(timer);el('loginSection').classList.remove('hidden');el('accountSection').classList.add('hidden');el('incidentsSection').classList.add('hidden');status('loginStatus','已登出。若已訂閱，請先在此裝置按「停用」，否則原訂閱仍可能保留。');});
if(token)connect();

// XZ_DEVICE_FINGERPRINT_V1
async function showDeviceFingerprint(){
 const target=el('deviceFingerprint');if(!target)return;
 try{
  if(!reg)await initSW();
  const sub=await reg.pushManager.getSubscription();
  if(!sub){target.textContent='本機未訂閱通知';return;}
  const bytes=new TextEncoder().encode(sub.endpoint);
  const hash=await crypto.subtle.digest('SHA-256',bytes);
  const fp=Array.from(new Uint8Array(hash)).map(x=>x.toString(16).padStart(2,'0')).join('').slice(0,16).toUpperCase();
  target.textContent='本機指紋碼：'+fp;
  target.dataset.fp=fp;
 }catch(e){target.textContent='無法讀取本機指紋碼：'+e.message;}
}
el('copyDeviceFingerprint').addEventListener('click',async()=>{
 const fp=el('deviceFingerprint')?.dataset.fp;
 if(!fp)return;
 try{await navigator.clipboard.writeText(fp);status('copyDeviceFingerprintResult','已複製指紋碼');}
 catch(e){status('copyDeviceFingerprintResult','請長按指紋碼自行複製');}
});

// XZ_LOCAL_NOTIFICATION_DIAG_V1
(function(){
 const button=document.getElementById('xzLocalNoticeButton');
 const output=document.getElementById('xzLocalNoticeResult');
 if(!button||!output)return;
 button.addEventListener('click',async()=>{
  button.disabled=true;
  try{
   if(!window.isSecureContext)throw Error('HTTPS_REQUIRED');
   if(!('Notification' in window)||!('serviceWorker' in navigator))throw Error('BROWSER_NOT_SUPPORTED');
   let permission=Notification.permission;
   if(permission==='default')permission=await Notification.requestPermission();
   if(permission!=='granted')throw Error('NOTIFICATION_PERMISSION_'+permission.toUpperCase());
   const registration=await navigator.serviceWorker.register('/api/jiaan1030/alert-sw.js',{scope:'/api/jiaan1030/'});
   await navigator.serviceWorker.ready;
   await registration.showNotification('小照｜本機顯示測試（非緊急）',{
    body:'這則通知只由你的手機瀏覽器產生，沒有緊急事件，也沒有從伺服器發送。',
    tag:'xz-local-diagnostic-'+Date.now(),
    icon:'/api/jiaan1030/alert-icon-192.png',
    data:{url:'/api/jiaan1030/alert-app'}
   });
   const sub=await registration.pushManager?.getSubscription();
   output.textContent='PASS: LOCAL_NOTIFICATION_API_CALLED; 訂閱='+Boolean(sub)+'；請檢查手機通知欄。這不保證系統實際顯示。';
  }catch(e){output.textContent='FAILED: '+(e?.message||String(e));}
  finally{button.disabled=false;}
 });
})();
