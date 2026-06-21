/* Sorento CRM service worker (TCK-33).
 * Push-focused: handles `push` + `notificationclick`. No fetch handler, so
 * /api/v1/* responses are NEVER cached (auth + freshness). Installability comes
 * from the manifest + this registered worker. */

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: 'Sorento', body: event.data ? event.data.text() : '' };
  }
  const title = data.title || 'Sorento';
  const options = {
    body: data.body || '',
    icon: '/sorento-app-logo.png',
    badge: '/sorento-app-logo.png',
    data: data.data || {},
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const link = (event.notification.data && event.notification.data.link) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if ('focus' in w) {
          if ('navigate' in w) {
            try { w.navigate(link); } catch (e) { /* cross-origin / unsupported */ }
          }
          return w.focus();
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(link);
      return undefined;
    }),
  );
});
