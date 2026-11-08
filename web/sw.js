const CACHE = 'sconto-shell-__SCONTO_VERSION__';
const SHELL = ['index.html', 'styles.css', 'app.mjs', 'motor.mjs', 'datos.mjs', 'manifest.webmanifest',
  'icons/icon-192.png', 'icons/icon-512.png', 'icons/apple-touch-icon.png', 'icons/logo.svg'];
const urls = new Set(SHELL.map(p => new URL(p, self.registration.scope).href));

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
});
self.addEventListener('message', event => {
  if (event.data === 'ACTIVAR') self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const nombre of await caches.keys()) if (nombre.startsWith('sconto-shell-') && nombre !== CACHE) await caches.delete(nombre);
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || new URL(event.request.url).origin !== location.origin) return;
  if (event.request.mode === 'navigate' && event.request.url.startsWith(self.registration.scope)) {
    event.respondWith(caches.open(CACHE).then(cache => cache.match('index.html')));
  } else if (urls.has(event.request.url)) {
    event.respondWith(caches.open(CACHE).then(async cache => (await cache.match(event.request)) || fetch(event.request)));
  }
});
