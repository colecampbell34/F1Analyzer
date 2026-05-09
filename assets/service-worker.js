const CACHE_NAME = 'f1-analyzer-assets-v11';
const STATIC_ASSETS = [
    '/assets/manifest.json',
    '/assets/custom.css',
    '/assets/scripts.js',
    '/assets/icon-192.png',
    '/assets/icon-512.png'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(STATIC_ASSETS))
            .catch(() => undefined)
    );
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => Promise.all(
            keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
        ))
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    const request = event.request;
    if (request.method !== 'GET') return;

    const url = new URL(request.url);
    const isAsset = url.origin === self.location.origin && url.pathname.startsWith('/assets/');
    if (!isAsset) return;

    event.respondWith(
        caches.match(request).then(cached => {
            const refreshed = fetch(request).then(response => {
                const copy = response.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
                return response;
            }).catch(() => cached);
            return cached || refreshed;
        })
    );
});
