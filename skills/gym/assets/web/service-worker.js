const CACHE = 'gympilot-shell-v22';
const SHELL = [
  '/',
  '/index.html',
  '/styles.css',
  '/app.js',
  '/manifest.webmanifest?v=20',
  '/icons/icon.svg',
  '/icons/icon-192-v20.png',
  '/icons/icon-512-v20.png',
  '/icons/apple-touch-icon.png',
  '/apple-touch-icon-v20.png',
  '/apple-touch-icon-precomposed-v20.png',
  '/icons/favicon-32.png',
  '/favicon.ico',
];

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await Promise.all(SHELL.map(async path => {
      const response = await fetch(new Request(path, {cache: 'reload'}));
      if (!response.ok) throw new Error(`Shell-Datei konnte nicht geladen werden: ${path}`);
      await cache.put(path, response);
    }));
  })());
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(
      keys.filter(key => key.startsWith('gympilot-shell-') && key !== CACHE).map(key => caches.delete(key)),
    )),
    self.clients.claim(),
  ]));
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(event.request, {cache: 'no-store'}));
    return;
  }
  if (url.origin === location.origin && url.pathname.startsWith('/install/')) {
    event.respondWith(fetch(event.request, {cache: 'no-store'}));
    return;
  }
  if (event.request.method !== 'GET' || url.origin !== location.origin) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(caches.open(CACHE).then(cache => cache.match('/index.html')).then(cached => cached || fetch('/index.html', {cache: 'reload'})));
    return;
  }
  event.respondWith(caches.open(CACHE).then(cache => cache.match(event.request)).then(cached => cached || fetch(event.request).then(response => {
    if (response.ok) caches.open(CACHE).then(cache => cache.put(event.request, response.clone()));
    return response;
  })));
});
