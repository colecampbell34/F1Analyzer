const CACHE_NAME = 'f1-analyzer-shell-v6';
const APP_SHELL = [
    '/',
    '/m',
    '/assets/manifest.json',
    '/assets/custom.css',
    '/assets/scripts.js',
    '/assets/icon-192.png',
    '/assets/icon-512.png'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(APP_SHELL))
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
    const isShellRoute = url.origin === self.location.origin && (url.pathname === '/' || url.pathname === '/m');
    const isAsset = url.origin === self.location.origin && url.pathname.startsWith('/assets/');

    if (isShellRoute) {
        event.respondWith(
            fetch(request)
                .then(response => {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
                    return response;
                })
                .catch(() => caches.match(request).then(cached => cached || caches.match('/m')))
        );
        return;
    }

    if (isAsset) {
        event.respondWith(
            caches.match(request).then(cached => cached || fetch(request).then(response => {
                const copy = response.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
                return response;
            }))
        );
    }
});
