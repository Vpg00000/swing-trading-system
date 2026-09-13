/* Service Worker for Swing Trading System PWA (TASK-118, TASK-120, TASK-121) */

const CACHE_NAME = 'swing-trading-v1';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/manifest.json',
    '/static/style.css',
    '/static/app.js',
    '/style.css',
    '/app.js'
];

// Install Event: Pre-cache core static assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[ServiceWorker] Pre-caching static assets');
            return cache.addAll(STATIC_ASSETS).catch(err => {
                console.warn('[ServiceWorker] Pre-caching warning:', err);
            });
        })
    );
    self.skipWaiting();
});

// Activate Event: Clean up outdated caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cache) => {
                    if (cache !== CACHE_NAME) {
                        console.log('[ServiceWorker] Removing old cache:', cache);
                        return caches.delete(cache);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// Fetch Event: Cache-First Strategy for static assets with sub-10ms response time
self.addEventListener('fetch', (event) => {
    // Only intercept GET requests
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);

    // Bypass API requests to network-first strategy with offline cache fallback
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request).catch(() => {
                return caches.match(event.request);
            })
        );
        return;
    }

    // Static Assets & Web Fonts: Cache-First Strategy (Sub-10ms interceptor)
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) {
                // Return cached asset immediately (< 10ms response time)
                return cachedResponse;
            }

            // Fetch from network if asset is not pre-cached
            return fetch(event.request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const responseClone = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseClone);
                    });
                }
                return networkResponse;
            }).catch((err) => {
                console.warn('[ServiceWorker] Fetch failed, serving offline page if available:', err);
                if (event.request.headers.get('accept') && event.request.headers.get('accept').includes('text/html')) {
                    return caches.match('/') || caches.match('/index.html');
                }
            });
        })
    );
});
