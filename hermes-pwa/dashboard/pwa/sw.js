/* hermes-pwa service worker: guarda a casca do app para abrir mesmo sem rede e mostrar a tela de
   login quando a sessão do dashboard expirou (401). Nada de API é cacheado.
   A casca é buscada primeiro na rede: uma atualização do plugin aparece na abertura seguinte. */
const VERSION = "hermes-pwa-v10";
const SHELL = ["./", "app.js", "app.css", "manifest.webmanifest", "icon.svg", "icon-192.png", "icon-512.png"];
const BASE = new URL("./", self.location.href).pathname;   // /api/plugins/hermes-pwa/

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL.map((u) => new Request(u, { cache: "reload" })))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.indexOf(BASE) !== 0) return;
  const rest = url.pathname.slice(BASE.length);
  if (rest.indexOf("api/") === 0 || rest === "qr.svg") return;   // dados: sempre direto da rede
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then((r) => {
      if (r.status === 401 || r.status === 403) return caches.match("./").then((c) => c || r);
      return r;
    }).catch(() => caches.match("./")));
    return;
  }
  e.respondWith(fetch(req, { cache: "no-store" }).then((r) => {
    if (r.ok) { const copy = r.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); }
    return r;
  }).catch(() => caches.match(req)));
});
