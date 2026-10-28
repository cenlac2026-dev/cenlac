// CENLAC: service worker mínimo para instalar la aplicación.
// Los datos siempre se piden al servidor (nada de salud queda guardado en el dispositivo);
// solo se guardan el estilo, los íconos y la página "sin conexión".
const CACHE = 'cenlac-v1';
const BASICOS = ['/static/estilos.css', '/static/logo.svg', '/static/iconos/icono-192.png', '/static/sin-conexion.html'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(BASICOS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match('/static/sin-conexion.html')));
  } else if (url.pathname.startsWith('/static/')) {
    e.respondWith(fetch(req).then(r => {
      const copia = r.clone();
      caches.open(CACHE).then(c => c.put(req, copia));
      return r;
    }).catch(() => caches.match(req)));
  }
});
