// Registers the service worker (installable PWA + offline fallback).
// Its URL comes from this script tag's data-sw attribute so the
// template, not this file, owns the route.
(function () {
  "use strict";

  if (!("serviceWorker" in navigator)) {
    return;
  }
  var script = document.currentScript;
  var url = script && script.getAttribute("data-sw");
  if (!url) {
    return;
  }
  window.addEventListener("load", function () {
    navigator.serviceWorker.register(url, { scope: "/" }).catch(function () {
      // Registration failing (e.g. private browsing) only loses the
      // offline page — the app itself works exactly the same.
    });
  });
})();
