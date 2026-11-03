// A search box for a long dropdown (Phase 22; made visible in 22.5).
//
// Enhancement, not the feature: without this script the box stays
// hidden and the select works exactly as it always has, which is why
// the template renders it with `hidden` and this removes that rather
// than building the markup here.
//
// Options are removed and re-added rather than hidden with CSS: an
// `<option>` with `display: none` is honoured by some browsers and
// ignored by others, and a dropdown that silently fails to filter is
// worse than one with no box at all.
//
// **Two things were wrong with the first version, and both made it
// look broken** (owner report, 2026-11-03: "nothing happens"):
//
//   1. It filtered a collapsed `<select size=1>`. The list was correct
//      but invisible until you opened the dropdown, so typing appeared
//      to do nothing at all. The select is now grown into a visible
//      list while the box has text.
//   2. Options read "Homeowner, Pat" and matching was one substring,
//      so "Pat Homeowner" and "Pat H" — the natural things to type —
//      matched nothing and emptied the list. Matching is now
//      token-by-token against a comma-free copy of the text, so the
//      order you type the names in does not matter.
(function () {
  "use strict";

  // Enough rows to be worth looking at, few enough to leave the rest
  // of the form on screen on a phone.
  var VISIBLE_ROWS = 8;

  // "Homeowner, Pat" -> "homeowner pat". Commas and runs of whitespace
  // go, so every token can be looked for on its own.
  function flatten(text) {
    return text.replace(/,/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function matches(haystack, needles) {
    for (var i = 0; i < needles.length; i++) {
      if (haystack.indexOf(needles[i]) === -1) {
        return false;
      }
    }
    return true;
  }

  var boxes = document.querySelectorAll("[data-filter-for]");
  Array.prototype.forEach.call(boxes, function (box) {
    var select = document.getElementById(box.dataset.filterFor);
    var input = box.querySelector("input");
    if (!select || !input) {
      return;
    }
    // The full list, kept because filtering empties the select.
    var options = Array.prototype.slice.call(select.options);
    // Flattened once, not per keystroke.
    var flattened = options.map(function (option) {
      return flatten(option.text);
    });
    // Real choices, ignoring the blank "---------" Django adds.
    var total = options.filter(function (option) {
      return option.value !== "";
    }).length;
    var status = box.querySelector("[data-filter-count]");
    box.hidden = false;

    // Enter submits the form a field sits in, and this box sits inside
    // the job form: pressing it while narrowing the list would save a
    // half-written job. There is nothing here to submit, so Enter does
    // nothing at all.
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
      }
    });

    input.addEventListener("input", function () {
      var needles = flatten(input.value).split(" ").filter(Boolean);
      // Whatever is chosen stays choosable, always. Filtering a
      // selected option out of the list would change what the form
      // submits without the person touching the dropdown.
      var chosen = select.value;
      var shown = 0;
      select.textContent = "";
      options.forEach(function (option, index) {
        var keep =
          !needles.length ||
          option.value === "" ||
          option.value === chosen ||
          matches(flattened[index], needles);
        if (keep) {
          select.appendChild(option);
          if (option.value !== "") {
            shown += 1;
          }
        }
      });
      select.value = chosen;

      // Show the result instead of leaving it folded away inside a
      // closed dropdown. `size` on a single select turns it into a
      // list box, which is plain HTML and needs no styling to work.
      if (needles.length) {
        select.size = Math.max(2, Math.min(VISIBLE_ROWS, select.options.length));
      } else {
        // Remove rather than set to 1: a select with no `size` reports
        // 0, so assigning 1 would leave it in a state it was never in.
        // Both render as a closed dropdown, but this returns it to
        // exactly what the server sent.
        select.removeAttribute("size");
      }

      if (status) {
        if (!needles.length) {
          status.textContent = "";
        } else if (shown === 0) {
          status.textContent = "No customers match.";
        } else {
          status.textContent = shown + " of " + total + " shown.";
        }
      }
    });
  });
})();
