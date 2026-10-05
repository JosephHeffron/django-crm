// App shell behavior (Phase 17.5, ADR 0010). Progressive enhancement:
// without this script the drawer links jump to #sidebar, the flyouts
// and menus are plain <details>, the theme button is a form post, and
// the search box submits to the search page (static/css/nojs.css).
(function () {
  "use strict";

  var body = document.body;
  var root = document.documentElement;
  var sidebar = document.getElementById("sidebar");
  var backdrop = document.querySelector("[data-nav-backdrop]");
  var desktop = window.matchMedia("(min-width: 1024px)");
  var darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

  function all(selector, scope) {
    return Array.prototype.slice.call((scope || document).querySelectorAll(selector));
  }

  function isTyping(el) {
    if (!el) {
      return false;
    }
    var tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
  }

  // ---------- Drawer (phones and tablets) ----------

  var toggles = all("[data-nav-toggle]");
  var lastFocus = null;

  function setExpanded(value) {
    toggles.forEach(function (el) {
      el.setAttribute("aria-expanded", value ? "true" : "false");
    });
  }

  function openDrawer() {
    lastFocus = document.activeElement;
    body.classList.add("nav-open");
    if (backdrop) {
      backdrop.hidden = false;
    }
    setExpanded(true);
    var first = sidebar && sidebar.querySelector("a, button, summary");
    if (first) {
      first.focus();
    }
  }

  function closeDrawer() {
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
        closeDrawer();
      } else {
        openDrawer();
      }
    });
    activateOnSpace(el);
  });

  all("[data-nav-close]").forEach(function (el) {
    el.addEventListener("click", function (event) {
      event.preventDefault();
      closeDrawer();
    });
    activateOnSpace(el);
  });

  if (backdrop) {
    backdrop.addEventListener("click", closeDrawer);
  }

  // Growing past the drawer breakpoint (rotating a tablet) shouldn't
  // leave an invisible open drawer and backdrop behind.
  desktop.addEventListener("change", function (event) {
    if (event.matches) {
      closeDrawer();
    }
  });

  // ---------- Sidebar collapse (desktop) ----------
  // Remembered in a cookie the server reads, so the next page renders
  // collapsed from its first paint.

  all("[data-sidebar-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!desktop.matches) {
        closeDrawer();
        return;
      }
      var collapsed = body.classList.toggle("sidebar-collapsed");
      button.setAttribute("aria-pressed", collapsed ? "true" : "false");
      document.cookie =
        "crm_sidebar=" + (collapsed ? "collapsed" : "expanded") + "; path=/; max-age=31536000; SameSite=Lax";
    });
  });

  // ---------- Flyouts and dropdowns (<details>) ----------
  // One open at a time; close on a click elsewhere or Escape.

  var disclosures = all("[data-nav-group], [data-dropdown]");

  function closeDisclosures(except) {
    disclosures.forEach(function (el) {
      if (el !== except && el.open) {
        el.open = false;
      }
    });
  }

  disclosures.forEach(function (el) {
    el.addEventListener("toggle", function () {
      if (el.open) {
        closeDisclosures(el);
      }
    });
  });

  document.addEventListener("click", function (event) {
    disclosures.forEach(function (el) {
      if (el.open && !el.contains(event.target)) {
        el.open = false;
      }
    });
  });

  // ---------- Theme ----------

  function effectiveTheme() {
    var chosen = root.getAttribute("data-theme");
    if (chosen === "light" || chosen === "dark") {
      return chosen;
    }
    return darkQuery.matches ? "dark" : "light";
  }

  function syncThemeControls() {
    var dark = effectiveTheme() === "dark";
    all("[data-theme-form] [role='switch']").forEach(function (el) {
      el.setAttribute("aria-checked", dark ? "true" : "false");
    });
  }

  all("[data-theme-form]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var next = effectiveTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      syncThemeControls();
      var data = new FormData(form);
      data.set("theme", next);
      fetch(form.action, {
        method: "POST",
        body: data,
        headers: { "X-Requested-With": "fetch" },
        credentials: "same-origin",
      });
    });
  });
  syncThemeControls();
  darkQuery.addEventListener("change", syncThemeControls);

  // ---------- Command palette (⌘K / Ctrl+K) ----------

  var palette = document.getElementById("palette");
  var input = palette && palette.querySelector("[data-palette-input]");
  var resultsList = palette && palette.querySelector("[data-palette-results]");
  var commands = palette ? all(".palette-item", palette.querySelector("[data-palette-commands]")) : [];
  var suggestUrl = palette && palette.getAttribute("data-suggest-url");
  var searchUrl = palette && palette.getAttribute("data-search-url");
  var selected = -1;
  var timer = null;
  var requestId = 0;

  function visibleItems() {
    return all(".palette-item", palette).filter(function (el) {
      return !el.hidden;
    });
  }

  function select(index) {
    var items = visibleItems();
    items.forEach(function (el) {
      el.classList.remove("is-selected");
    });
    if (!items.length) {
      selected = -1;
      return;
    }
    selected = (index + items.length) % items.length;
    items[selected].classList.add("is-selected");
    items[selected].scrollIntoView({ block: "nearest" });
  }

  function filterCommands(text) {
    var needle = text.trim().toLowerCase();
    commands.forEach(function (el) {
      el.parentNode.hidden = needle !== "" && el.textContent.toLowerCase().indexOf(needle) === -1;
      el.hidden = el.parentNode.hidden;
    });
  }

  function renderResults(rows) {
    while (resultsList.firstChild) {
      resultsList.removeChild(resultsList.firstChild);
    }
    rows.forEach(function (row) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.className = "palette-item";
      a.href = row.url;
      var label = document.createElement("span");
      label.textContent = row.label;
      var detail = document.createElement("span");
      detail.className = "palette-detail";
      detail.textContent = row.detail || "";
      var kind = document.createElement("span");
      kind.className = "palette-kind";
      kind.textContent = row.kind;
      a.appendChild(label);
      a.appendChild(detail);
      a.appendChild(kind);
      li.appendChild(a);
      resultsList.appendChild(li);
    });
  }

  function suggest(text) {
    if (!suggestUrl) {
      return;
    }
    clearTimeout(timer);
    if (text.trim().length < 2) {
      renderResults([]);
      select(0);
      return;
    }
    timer = setTimeout(function () {
      var mine = ++requestId;
      fetch(suggestUrl + "?q=" + encodeURIComponent(text.trim()), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (response) {
          return response.ok ? response.json() : { results: [] };
        })
        .then(function (data) {
          if (mine === requestId) {
            renderResults(data.results || []);
            select(0);
          }
        })
        .catch(function () {});
    }, 180);
  }

  function openPalette(prefill) {
    if (!palette || typeof palette.showModal !== "function") {
      return false;
    }
    closeDrawer();
    closeDisclosures(null);
    if (!palette.open) {
      palette.showModal();
    }
    input.value = prefill || "";
    filterCommands(input.value);
    renderResults([]);
    suggest(input.value);
    select(0);
    input.focus();
    return true;
  }

  if (palette) {
    input.addEventListener("input", function () {
      filterCommands(input.value);
      suggest(input.value);
      select(0);
    });

    input.addEventListener("keydown", function (event) {
      // Close on the first Escape ourselves: Chrome can swallow the
      // dialog's own Escape when it was opened from a keystroke.
      if (event.key === "Escape") {
        event.preventDefault();
        palette.close();
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        select(selected + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        select(selected - 1);
      } else if (event.key === "Enter") {
        event.preventDefault();
        var items = visibleItems();
        if (selected >= 0 && items[selected]) {
          window.location.href = items[selected].href;
        } else if (searchUrl && input.value.trim()) {
          window.location.href = searchUrl + "?q=" + encodeURIComponent(input.value.trim());
        }
      }
    });

    // A click on the backdrop (outside the dialog box) closes it.
    palette.addEventListener("click", function (event) {
      if (event.target === palette) {
        palette.close();
      }
    });

    // Open from the search pill on a click or when typing starts — not
    // on focus: closing the dialog hands focus back to the pill, and a
    // focus trigger would reopen it straight away.
    all("[data-palette-trigger]").forEach(function (el) {
      if (el.tagName === "INPUT") {
        el.addEventListener("click", function () {
          openPalette(el.value);
        });
        el.addEventListener("keydown", function (event) {
          if (event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey) {
            event.preventDefault();
            openPalette(el.value + event.key);
          }
        });
      } else {
        el.addEventListener("click", function () {
          openPalette("");
        });
      }
    });
  }

  // ---------- Keyboard shortcuts ----------
  // Ctrl/⌘+K: palette. Two-key sequences (g c, n t …) follow the links
  // the page rendered for this person, so they respect roles. "?": help.

  var pending = null;
  var pendingTimer = null;

  document.addEventListener("keydown", function (event) {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      if (openPalette("")) {
        event.preventDefault();
      }
      return;
    }
    if (event.key === "Escape") {
      closeDrawer();
      closeDisclosures(null);
      return;
    }
    if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) {
      return;
    }
    if (palette && palette.open) {
      return;
    }
    var key = event.key.toLowerCase();
    if (key === "?") {
      var help = document.querySelector(".help-fab");
      if (help) {
        help.open = !help.open;
      }
      return;
    }
    if (pending) {
      // Only letters complete a shortcut (and only letters ever reach the
      // selector below).
      var target = /^[a-z]$/.test(key)
        ? document.querySelector('[data-shortcut="' + pending + " " + key + '"]')
        : null;
      pending = null;
      clearTimeout(pendingTimer);
      if (target) {
        event.preventDefault();
        window.location.href = target.href;
      }
      return;
    }
    if (key === "g" || key === "n") {
      pending = key;
      pendingTimer = setTimeout(function () {
        pending = null;
      }, 1200);
    }
  });
})();
