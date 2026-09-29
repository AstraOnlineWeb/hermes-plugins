/* hermes-pwa service worker: guarda a casca do app para abrir rápido e mostrar a tela de login
   mesmo quando a sessão do dashboard expirou (401). Nada de API é cacheado. */
const VERSION = "hermes-pwa-v8";
const SHELL = ["./", "app.js", "app.css", "manifest.webmanifest", "icon.svg", "icon-192.png", "icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.pathname.includes("/api/sessions") || url.pathname.endsWith("/api/me") || url.pathname.includes("/qr.svg")) return;
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then((r) => {
      if (r.status === 401 || r.status === 403) return caches.match("./").then((c) => c || r);
      return r;
    }).catch(() => caches.match("./")));
    return;
  }
  e.respondWith(caches.match(req).then((cached) => {
    const net = fetch(req).then((r) => { if (r.ok) caches.open(VERSION).then((c) => c.put(req, r.clone())); return r; }).catch(() => cached);
    return cached || net;
  }));
});
