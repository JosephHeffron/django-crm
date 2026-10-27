// A search box for a long dropdown (Phase 22).
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
(function () {
  "use strict";

  var boxes = document.querySelectorAll("[data-filter-for]");
  Array.prototype.forEach.call(boxes, function (box) {
    var select = document.getElementById(box.dataset.filterFor);
    var input = box.querySelector("input");
    if (!select || !input) {
      return;
    }
    // The full list, kept because filtering empties the select.
    var options = Array.prototype.slice.call(select.options);
    box.hidden = false;

    input.addEventListener("input", function () {
      var needle = input.value.trim().toLowerCase();
      // Whatever is chosen stays choosable, always. Filtering a
      // selected option out of the list would change what the form
      // submits without the person touching the dropdown.
      var chosen = select.value;
      select.textContent = "";
      options.forEach(function (option) {
        var keep =
          !needle ||
          option.value === "" ||
          option.value === chosen ||
          option.text.toLowerCase().indexOf(needle) > -1;
        if (keep) {
          select.appendChild(option);
        }
      });
      select.value = chosen;
    });
  });
})();
