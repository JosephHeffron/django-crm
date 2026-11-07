// Marks the page you are on in the site navigation.
//
// Progressive: with this script blocked or failed, every link still
// works; the current page just is not highlighted. Nothing else on the
// site depends on JavaScript.
(function () {
  "use strict";

  // "/services.html" and "/services" are the same page (Caddy serves
  // clean URLs through try_files), and "/index.html" is "/".
  var here = window.location.pathname.replace(/\.html$/, "").replace(/\/index$/, "/");
  if (here.length > 1) {
    here = here.replace(/\/$/, "");
  }

  var links = document.querySelectorAll(".site-nav a[href]");
  for (var i = 0; i < links.length; i++) {
    if (links[i].getAttribute("href") === here) {
      links[i].setAttribute("aria-current", "page");
    }
  }
})();
