{% autoescape off %}// Service worker — rendered by apps/core/views.py:ServiceWorkerView.
// Caches ONLY the static app shell and the offline page. Authenticated
// pages are never cached: crew phones are shared, and a cached customer
// page must not outlive the session that loaded it.
"use strict";

const VERSION = "{{ version }}";
const CACHE = "crm-shell-" + VERSION;
const OFFLINE_URL = "{{ offline_url }}";
const PRECACHE = {{ precache_json }};
// Under DEBUG, assets are network-first so a CSS edit shows up on the
// next load instead of after a service-worker update cycle.
const NETWORK_FIRST_ASSETS = {{ network_first_assets|yesno:"true,false" }};

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll([OFFLINE_URL, ...PRECACHE]))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith("crm-shell-") && key !== CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function cacheFirst(request) {
  return caches.match(request).then((hit) => hit || fetch(request));
}

function networkFirst(request) {
  return fetch(request)
    .then((response) => {
      const copy = response.clone();
      caches.open(CACHE).then((cache) => cache.put(request, copy));
      return response;
    })
    .catch(() => caches.match(request));
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    return;
  }
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }
  if (PRECACHE.includes(url.pathname)) {
    event.respondWith(NETWORK_FIRST_ASSETS ? networkFirst(request) : cacheFirst(request));
  }
});
{% endautoescape %}
