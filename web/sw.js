/* GPlanSiS|COMEX — service worker
   Shell em cache (abre offline), navegação rede-primeiro, fontes cache-primeiro, /api/ e /auth/ nunca em cache. */
const VERSAO = 'gpscomex-v9';
const FONTES = VERSAO + '-fontes';
const SHELL = ['./', './index.html', './app.html', './manifest.webmanifest', './icons/icon-192.png', './icons/icon-512.png',
               './icons/maskable-512.png', './icons/apple-touch-icon.png', './icons/favicon.svg', './icons/favicon-32.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSAO).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== VERSAO && k !== FONTES).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin === location.origin && url.pathname.includes('/api/')) return;   // dado vivo: sempre rede
  if (url.origin === location.origin && url.pathname.startsWith('/auth/')) return;  // Keycloak na mesma origem: nunca em cache
  if (req.mode === 'navigate') {
    // landing (/) e app (/app.html) têm cache próprio; offline, o app abre a partir do shell
    const pagina = url.pathname.endsWith('/app.html') ? './app.html' : './index.html';
    e.respondWith(fetch(req).then(r => {
      if (r.ok && !url.search.includes('code=')) { const cp = r.clone(); caches.open(VERSAO).then(c => c.put(pagina, cp)); }
      return r;
    }).catch(() => caches.match(pagina)));
    return;
  }
  if (url.host === 'fonts.googleapis.com' || url.host === 'fonts.gstatic.com') {
    e.respondWith(caches.open(FONTES).then(async c => {
      const hit = await c.match(req);
      const net = fetch(req).then(r => { if (r.ok || r.type === 'opaque') c.put(req, r.clone()); return r; }).catch(() => hit);
      return hit || net;
    }));
    return;
  }
  if (url.origin === location.origin) {
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => {
      if (r.ok) { const cp = r.clone(); caches.open(VERSAO).then(c => c.put(req, cp)); }
      return r;
    })));
  }
});
