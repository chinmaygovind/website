/* Service worker: cache static assets so the game is installable and the 1.3MB
   three.js bundle is not refetched every session. It deliberately never
   intercepts pages, POSTs or socket.io traffic, so live racing and time
   submission always go straight to the network. */
const CACHE = "drive-v6";
const ASSETS = [
  "/static/css/style.css",
  "/static/js/game.js",
  // On every page, and the thing that hands a guest's times over once they have
  // an account - so it has to work on the flaky connection that made them a
  // guest's times in the first place.
  "/static/js/pending.js",
  "/static/js/physics.js",
  "/static/js/trackmesh.js",
  "/static/js/course.js",
  "/static/js/render.js",
  "/static/js/sound.js",
  "/static/js/vendor/three.module.js",
  "/static/fonts/titillium-400.woff2",
  "/static/fonts/titillium-600.woff2",
  "/static/fonts/titillium-700.woff2",
  "/static/fonts/titillium-900.woff2",
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
