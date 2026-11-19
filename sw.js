// Orri — service worker : l'application s'ouvre même sans réseau.
// (Les cartes et données hors ligne du trek arriveront en semaine 7.)
const VERSION = 'orri-v1.12.0';
const SHELL = [
  './', './index.html', './manifest.webmanifest',
  './icons/icon-192.png', './icons/icon-512.png', './icons/maskable-512.png', './icons/favicon-32.png', './fonts/figtree.woff2', './fonts/fraunces.woff2', './carte/orri-style.json', './carte/monde.json', './carte/relief.jpg'
];
const CDN = [
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js',
  'https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css',
  'https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js',
  'https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.1.4/leaflet-maplibre-gl.js',
  'https://unpkg.com/d3-array@3.2.4/dist/d3-array.min.js',
  'https://unpkg.com/d3-geo@3.1.1/dist/d3-geo.min.js',
  'https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.js'
];

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const c = await caches.open(VERSION);
    await c.addAll(SHELL);
    await Promise.all(CDN.map(u => c.add(new Request(u, { mode: 'no-cors' })).catch(() => {})));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== VERSION && k !== TERR) await caches.delete(k);
    await self.clients.claim();
  })());
});

// Application et bibliothèque : réseau d'abord (pour avoir la dernière version), cache si hors ligne.
// Tout le reste (cartes, itinéraires, OpenStreetMap) passe directement par le réseau.
// Altitudes du globe 3D et des souvenirs (AWS Terrain Tiles) : cache d'abord, 1 500 tuiles au plus (~100 Mo),
// pour ne pas retélécharger le relief à chaque ouverture de l'accueil.
const TERR = 'orri-relief', TERR_MAX = 1500;
async function terrain(req) {
  const c = await caches.open(TERR), hit = await c.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res && res.ok) { c.put(req, res.clone()).then(async () => { const ks = await c.keys(); for (let i = 0; i < ks.length - TERR_MAX; i++) await c.delete(ks[i]); }).catch(() => {}); }
  return res;
}
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.hostname === 's3.amazonaws.com' && url.pathname.startsWith('/elevation-tiles-prod/')) return e.respondWith(terrain(req));
  const isShell = url.origin === self.location.origin || CDN.includes(req.url);
  if (!isShell) return;
  e.respondWith((async () => {
    const c = await caches.open(VERSION);
    try {
      const res = await fetch(req);
      if (res && (res.ok || res.type === 'opaque')) c.put(req, res.clone());
      return res;
    } catch (err) {
      return (await c.match(req, { ignoreSearch: true })) || (req.mode === 'navigate' ? await c.match('./index.html') : Response.error());
    }
  })());
});
