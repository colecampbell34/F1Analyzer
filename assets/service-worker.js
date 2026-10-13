// Do not cache Dash's mutable application shell or custom JS/CSS here.  Their
// URLs are stable between deployments, and a cache-first strategy can combine
// an old renderer with a new server response after a release.
const CACHE_NAME = 'f1-analyzer-static-v12';
const STATIC_ASSETS = [
    '/assets/manifest.json',
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
    const isCacheableStaticAsset = url.origin === self.location.origin &&
        /^\/assets\/icon-\d+\.png$/.test(url.pathname);
    if (!isCacheableStaticAsset) return;

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
