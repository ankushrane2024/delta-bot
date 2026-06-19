const CACHE_NAME = 'btc-bot-cache-v1';
const urlsToCache = [
  '/',
  '/history',
  '/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
      .catch(err => console.error('Cache error:', err))
  );
  self.skipWaiting();
});

self.addEventListener('fetch', event => {
  // Pass-through for API and WebSocket requests so live data isn't cached
  if (event.request.url.includes('/api/') || event.request.url.includes('socket')) {
    return;
  }
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
