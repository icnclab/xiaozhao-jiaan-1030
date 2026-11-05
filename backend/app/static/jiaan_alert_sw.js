"use strict";
// Explicit separation between authorized one-device test and real emergencies.
self.addEventListener('install', e => e.waitUntil(self.skipWaiting()));
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('push', event => {
  let p={}; try { p=event.data ? event.data.json() : {}; } catch(_e) {}
  const isTest=p.kind==='xz_controlled_test' && p.stage==='test';
  const id=/^[0-9a-f-]{36}$/i.test(String(p.emergency_id||'')) ? p.emergency_id : '';
  const label={new:'新緊急事件',unacknowledged_60s:'未接手已超過1分鐘',unacknowledged_180s:'未接手已超過3分鐘'}[p.stage]||'緊急事件';
  const title=isTest?'小照｜通知測試（非緊急）':'小照｜'+label;
  const body=isTest?'這是授權裝置的單次推播測試，沒有發生緊急通報。':'有緊急通報待確認，請立即開啟督導通知端。緊急狀況請直接電話求援。';
  const tag=isTest?'xz-controlled-test':(id?`xz-${id}-${p.stage||'new'}`:'xz-emergency');
  event.waitUntil(self.registration.showNotification(title,{body,tag,renotify:true,requireInteraction:!isTest,icon:'/api/jiaan1030/alert-icon-192.png',badge:'/api/jiaan1030/alert-icon-192.png',data:{url:'/api/jiaan1030/alert-app'}}));
});
self.addEventListener('notificationclick',event=>{event.notification.close();event.waitUntil((async()=>{const url=new URL('/api/jiaan1030/alert-app',self.location.origin).href;const windows=await clients.matchAll({type:'window',includeUncontrolled:true});for(const w of windows){if(w.url.startsWith(url)&&'focus' in w){await w.focus();return;}}if(clients.openWindow)await clients.openWindow(url);})());});
