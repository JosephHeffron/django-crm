// Line items on a job or estimate (Phase 17.5 step 5). Without this
// script the form still works: one blank row is always offered, and the
// server ignores rows left empty.
(function () {
  "use strict";

  var rows = document.querySelector("[data-line-rows]");
  var template = document.querySelector("[data-line-template]");
  var addButton = document.querySelector("[data-add-line]");
  if (!rows || !template || !addButton) {
    return;
  }
  var total = document.getElementById("id_lines-TOTAL_FORMS");
  if (!total) {
    return;
  }

  function fillPrice(row) {
    var service = row.querySelector("select[name$='-service_type']");
    var price = row.querySelector("input[name$='-unit_price']");
    if (!service || !price) {
      return;
    }
    service.addEventListener("change", function () {
      // Each option carries its service's default price (ServiceSelect
      // in apps/jobs/forms.py). Only fill a blank or auto-filled price,
      // never overwrite one somebody typed.
      var chosen = service.options[service.selectedIndex];
      var preset = chosen ? chosen.getAttribute("data-price") : "";
      if (!price.value || price.dataset.autofilled === "yes") {
        price.value = preset || "";
        price.dataset.autofilled = "yes";
      }
    });
    price.addEventListener("input", function () {
      price.dataset.autofilled = "no";
    });
  }

  Array.prototype.forEach.call(rows.querySelectorAll("[data-line-row]"), fillPrice);

  addButton.addEventListener("click", function () {
    var index = parseInt(total.value, 10);
    var holder = document.createElement("div");
    holder.innerHTML = template.innerHTML.replace(/__prefix__/g, String(index));
    var row = holder.firstElementChild;
    rows.appendChild(row);
    total.value = String(index + 1);
    fillPrice(row);
    var first = row.querySelector("select, input");
    if (first) {
      first.focus();
    }
  });
})();
