// The map page (Phase 17.5 step 8, ADR 0011). Leaflet is vendored and
// served from this origin; map images come from OpenStreetMap. Without
// this script the page still lists every placed address, so nothing is
// only reachable through the map.
(function () {
  "use strict";

  var holder = document.querySelector("[data-map]");
  if (!holder || typeof window.L === "undefined") {
    return;
  }

  var pins;
  try {
    pins = JSON.parse(holder.dataset.pins || "[]");
  } catch (error) {
    return;
  }
  if (!pins.length) {
    return;
  }

  var map = L.map(holder, { scrollWheelZoom: false });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    // Required by the OpenStreetMap tile usage policy.
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  function colour(pin) {
    if (pin.status === "completed") {
      return "#157a3a";
    }
    return pin.when ? "#2563eb" : "#64748b";
  }

  var bounds = [];
  pins.forEach(function (pin) {
    var marker = L.circleMarker([pin.lat, pin.lng], {
      radius: 8,
      color: "#ffffff",
      weight: 2,
      fillColor: colour(pin),
      fillOpacity: 1,
    }).addTo(map);

    // Built as DOM nodes, never as an HTML string: customer names and
    // addresses are people's data, and textContent can't be markup.
    var popup = document.createElement("div");
    var name = document.createElement("a");
    name.href = pin.url;
    name.textContent = pin.title;
    popup.appendChild(name);
    [pin.address, pin.when ? pin.service + " · " + pin.when : ""].forEach(function (line) {
      if (!line) {
        return;
      }
      var row = document.createElement("div");
      row.textContent = line;
      popup.appendChild(row);
    });
    marker.bindPopup(popup);
    bounds.push([pin.lat, pin.lng]);
  });

  map.fitBounds(bounds, { padding: [30, 30], maxZoom: 15 });

  // Clicking the map fills in the coordinates for an address that
  // OpenStreetMap can't find — which it can't, for a new estate or a
  // long driveway. This only saves typing: the two boxes are real form
  // fields and work on their own, so the feature exists without this
  // script (apps/jobs/templates/jobs/map.html).
  var pinForms = Array.prototype.slice.call(document.querySelectorAll("[data-pin-form]"));
  var active = pinForms.length ? pinForms[0] : null;

  pinForms.forEach(function (form) {
    // Whichever address you last touched is the one a click fills, so
    // a page with several unplaced addresses isn't ambiguous.
    form.addEventListener("focusin", function () {
      active = form;
      pinForms.forEach(function (other) {
        other.classList.toggle("is-active", other === form);
      });
    });
  });

  if (active) {
    active.classList.add("is-active");
  }

  map.on("click", function (event) {
    map.scrollWheelZoom.enable();
    if (!active || !event.latlng) {
      return;
    }
    var lat = active.querySelector("[data-pin-lat]");
    var lng = active.querySelector("[data-pin-lng]");
    if (!lat || !lng) {
      return;
    }
    // Six decimals is what the model stores; more would be dropped.
    lat.value = event.latlng.lat.toFixed(6);
    lng.value = event.latlng.lng.toFixed(6);
  });
})();
