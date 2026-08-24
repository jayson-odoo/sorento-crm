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

/* A message push carries `data.tag` ("contact-<respond_io_id>"); every other
 * notification does not, and takes the plain show-it path below unchanged. */

/* The contact a link points at: the `contact` query param from
 * /sla-management/conversations?contact=<id>. Null when the link names no
 * single contact. */
function threadKeyFromLink(link) {
  if (!link) return null;
  const queryAt = link.indexOf('?');
  if (queryAt === -1) return null;
  return new URLSearchParams(link.slice(queryAt + 1)).get('contact') || null;
}

function clientIsOnThread(url, threadKey) {
  const href = String(url || '');
  return href.indexOf('contact=' + threadKey) !== -1;
}

/* Decides what a push should put on screen, given the worker's registration and
 * client list. Split out of the listener so it can be tested without a browser
 * (components/pwa/sw-push.test.ts). */
async function handlePushPayload(payload, ctx) {
  const data = payload.data || {};
  const title = payload.title || 'Sorento';
  const options = {
    body: payload.body || '',
    icon: '/sorento-app-logo.png',
    badge: '/sorento-app-logo.png',
    data: data,
  };

  if (!data.tag) {
    await ctx.registration.showNotification(title, options);
    return { shown: true };
  }

  // Suppress: the thread is already on screen, so a buzz would be noise.
  const threadKey = threadKeyFromLink(data.link);
  if (threadKey) {
    const wins = await ctx.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const w of wins) {
      if (w.visibilityState === 'visible' && clientIsOnThread(w.url, threadKey)) {
        return { shown: false, reason: 'thread-visible' };
      }
    }
  }

  // Coalesce: one notification per contact, updated in place. The count has to
  // ride on the displayed notification's own data - nothing else survives.
  const displayed = await ctx.registration.getNotifications({ tag: data.tag });
  const previous = displayed.length ? displayed[displayed.length - 1] : null;
  const count = previous ? ((previous.data && previous.data.messageCount) || 1) + 1 : 1;

  options.tag = data.tag;
  options.renotify = true;
  options.data = Object.assign({}, data, { messageCount: count });
  if (count > 1) options.body = count + ' new messages';

  await ctx.registration.showNotification(title, options);
  return { shown: true };
}

function parsePushPayload(eventData) {
  try {
    return eventData ? eventData.json() : {};
  } catch (e) {
    return { title: 'Sorento', body: eventData ? eventData.text() : '' };
  }
}

self.addEventListener('push', (event) => {
  const payload = parsePushPayload(event.data);
  event.waitUntil(
    handlePushPayload(payload, { registration: self.registration, clients: self.clients }),
  );
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

/* Test seam only. `module` is undefined inside a real service worker, so this
 * block never runs there. */
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { handlePushPayload, parsePushPayload };
}
