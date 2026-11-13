/* XZ_SOS45_CLICK_V2 - isolated SOS notifications, safe deep-link target, forced takeover */
self.addEventListener('install', () => { self.skipWaiting(); });
self.addEventListener('activate', event => { event.waitUntil(clients.claim()); });
self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) {}
  const title = String(data.title || '小照｜緊急通報');
  const body = String(data.body || '有一筆緊急通報，請儘速確認，必要時依機構 SOP 電話聯繫');
  const tag = 'xz-sos-' + String(data.emergency_id || 'new') + '-' + String(data.stage || 'new');
  event.waitUntil(self.registration.showNotification(title, {
    body, tag, renotify: true,
    data: { url: '/api/jiaan1030/sos-app/' },
    icon: '/api/jiaan1030/alert-icon-192.png'
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil((async () => {
    const destination = new URL('/api/jiaan1030/sos-app/', self.location.origin);
    const windows = await clients.matchAll({type:'window', includeUncontrolled:true});
    for (const windowClient of windows) {
      if (new URL(windowClient.url).origin === destination.origin &&
          new URL(windowClient.url).pathname.startsWith('/api/jiaan1030/sos-app/')) {
        await windowClient.focus();
        return;
      }
    }
    await clients.openWindow(destination.href);
  })());
});
