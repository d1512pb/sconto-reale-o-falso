const CACHE = 'sconto-shell-__SCONTO_VERSION__';
const SHELL = ['index.html', 'styles.css', 'interfaz.css', 'app.mjs', 'motor.mjs', 'datos.mjs', 'api.mjs', 'interfaz.mjs', 'modelo.mjs', 'manifest.webmanifest',
  'icons/icon-192.png', 'icons/icon-512.png', 'icons/apple-touch-icon.png', 'icons/logo.svg'];
const OPCIONALES = ['modelo.json'];
const urls = new Set([...SHELL, ...OPCIONALES].map(p => new URL(p, self.registration.scope).href));

self.addEventListener('install', event => {
  const peticiones = SHELL.map(p => new Request(new URL(p, self.registration.scope), {cache: 'reload'}));
  event.waitUntil(caches.open(CACHE).then(async cache => {
    await cache.addAll(peticiones);
    // Archivos que pueden no existir en todas las publicaciones: su ausencia no impide instalar la app.
    for (const p of OPCIONALES) try { await cache.add(new Request(new URL(p, self.registration.scope), {cache: 'reload'})); } catch { /* opcional */ }
  }));
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
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== location.origin) return;
  // Sólo la portada de la app sale de la copia guardada; /docs y /v1 de la API van siempre a la red.
  const raiz = new URL(self.registration.scope).pathname;
  const portada = url.pathname === raiz || url.pathname === raiz + 'index.html';
  if (event.request.mode === 'navigate' && portada) {
    event.respondWith(caches.open(CACHE).then(cache => cache.match('index.html')));
  } else if (urls.has(event.request.url)) {
    event.respondWith(caches.open(CACHE).then(async cache => (await cache.match(event.request)) || fetch(event.request)));
  }
});
