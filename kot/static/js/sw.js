/* Service worker: cache static assets so the app is installable and loads fast.
   It deliberately never intercepts pages, POSTs, or socket.io traffic, so live
   gameplay always goes straight to the network. */
const CACHE = "kot-v1";
const ASSETS = [
  "/static/css/style.css",
  "/static/js/game.js",
  "/static/fonts/xkcd-script.woff",
  "/static/img/icon-192.png",
  "/static/img/icon.svg",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) =>
    Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (!url.pathname.startsWith("/static/")) return;   // only static assets
  // Network-first: always try fresh (so updates ship), fall back to cache offline.
  e.respondWith(
    fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy));
      return res;
    }).catch(() => caches.match(req))
  );
});
