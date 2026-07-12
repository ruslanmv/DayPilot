/* DayPilot Mobile service worker (batch B13).
 *
 * Caches the app shell for offline launch and keeps the last successful
 * /v1/today response so an offline reopen still shows the day's state. Sensitive
 * actions (approvals) are never served from cache — they require the network.
 */
const CACHE = 'daypilot-mobile-v1'
const APP_SHELL = ['/', '/index.html', '/manifest.webmanifest', '/daypilot-icon.svg']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(APP_SHELL)))
  self.skipWaiting() // update flow: activate the new SW immediately
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  )
  self.clients.claim()
})

self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') self.skipWaiting()
})

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  if (event.request.method !== 'GET') return

  // Today snapshot: network-first, fall back to the last cached copy offline.
  if (url.pathname === '/v1/today') {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const copy = res.clone()
          caches.open(CACHE).then((cache) => cache.put(event.request, copy))
          return res
        })
        .catch(() => caches.match(event.request)),
    )
    return
  }

  // Never serve approvals/writes from cache — they need a live connection.
  if (url.pathname.startsWith('/v1/approvals') || event.request.method !== 'GET') {
    return
  }

  // App shell + static assets: cache-first with a network fallback.
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request)),
  )
})

// Push-ready approval notifications (no-op until a push service is configured).
self.addEventListener('push', (event) => {
  let payload = { title: 'DayPilot', body: 'You have a pending approval.', url: '/' }
  try {
    if (event.data) payload = { ...payload, ...event.data.json() }
  } catch (e) {
    /* keep defaults */
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: '/daypilot-icon.svg',
      data: { url: payload.url },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = (event.notification.data && event.notification.data.url) || '/'
  event.waitUntil(self.clients.openWindow(target))
})
