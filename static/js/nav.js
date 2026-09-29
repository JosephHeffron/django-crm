// Off-canvas navigation drawer for phone/tablet widths. Progressive
// enhancement: every [data-nav-toggle] is a real link to #sidebar, so
// without this script the page still works (static/css/nojs.css).
(function () {
  "use strict";

  var body = document.body;
  var sidebar = document.getElementById("sidebar");
  var backdrop = document.querySelector("[data-nav-backdrop]");
  if (!sidebar) {
    return;
  }
  var toggles = Array.prototype.slice.call(document.querySelectorAll("[data-nav-toggle]"));
  var closers = Array.prototype.slice.call(document.querySelectorAll("[data-nav-close]"));
  var lastFocus = null;
  var desktop = window.matchMedia("(min-width: 1024px)");

  function setExpanded(value) {
    toggles.forEach(function (el) {
      el.setAttribute("aria-expanded", value ? "true" : "false");
    });
  }

  function open() {
    lastFocus = document.activeElement;
    body.classList.add("nav-open");
    if (backdrop) {
      backdrop.hidden = false;
    }
    setExpanded(true);
    var first = sidebar.querySelector("a, button");
    if (first) {
      first.focus();
    }
  }

  function close() {
    if (!body.classList.contains("nav-open")) {
      return;
    }
    body.classList.remove("nav-open");
    if (backdrop) {
      backdrop.hidden = true;
    }
    setExpanded(false);
    if (lastFocus && typeof lastFocus.focus === "function") {
      lastFocus.focus();
    }
  }

  // These controls are role="button" links (so they still work without
  // JS); real buttons also activate on Space, so match that.
  function activateOnSpace(el) {
    el.addEventListener("keydown", function (event) {
      if (event.key === " ") {
        event.preventDefault();
        el.click();
      }
    });
  }

  toggles.forEach(function (el) {
    el.addEventListener("click", function (event) {
      event.preventDefault();
      if (body.classList.contains("nav-open")) {
        close();
      } else {
        open();
      }
    });
    activateOnSpace(el);
  });

  closers.forEach(function (el) {
    el.addEventListener("click", function (event) {
      event.preventDefault();
      close();
    });
    activateOnSpace(el);
  });

  if (backdrop) {
    backdrop.addEventListener("click", close);
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      close();
    }
  });

  // Growing past the drawer breakpoint (rotating a tablet) shouldn't
  // leave an invisible open drawer and backdrop behind.
  desktop.addEventListener("change", function (event) {
    if (event.matches) {
      close();
    }
  });
})();
