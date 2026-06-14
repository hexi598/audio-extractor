// 视频音频提取 - Service Worker
// 缓存策略：静态资源 Cache-First，HTML Stale-While-Revalidate，API Network-Only
const CACHE = "audio-extract-v3";

// 需要预缓存的静态资源
const ASSETS = [
  "/",
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
];

// ---- Install: 预缓存核心静态资源 ----
self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS))
  );
  // 立即激活，不等待旧 SW
  self.skipWaiting();
});

// ---- Activate: 清理旧版本缓存 ----
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))
      );
    })
  );
  // 立即接管所有页面
  self.clients.claim();
});

// ---- Fetch: 分层缓存策略 ----
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // 策略1: API 请求 —— Network-Only，不做缓存
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  // 策略2: 静态资源 —— Cache-First
  if (
    url.pathname.startsWith("/static/") ||
    e.request.destination === "image" ||
    e.request.destination === "font"
  ) {
    e.respondWith(
      caches.match(e.request).then((cached) => cached || fetch(e.request))
    );
    return;
  }

  // 策略3: HTML / 导航请求 —— Stale-While-Revalidate
  // 立即返回缓存版本（快速加载），同时后台更新缓存
  if (
    e.request.mode === "navigate" ||
    e.request.destination === "document"
  ) {
    e.respondWith(
      caches.open(CACHE).then((cache) => {
        return cache.match(e.request).then((cached) => {
          const fetched = fetch(e.request).then((response) => {
            if (response.ok) {
              cache.put(e.request, response.clone());
            }
            return response;
          });
          return cached || fetched;
        });
      })
    );
    return;
  }

  // 策略4: 其他请求 —— Cache-First 兜底
  e.respondWith(
    caches.match(e.request).then((cached) => cached || fetch(e.request))
  );
});
