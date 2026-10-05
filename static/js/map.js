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
  // Scroll-zoom is off so the page still scrolls on a phone; a click
  // turns it on for people who want it.
  map.on("click", function () {
    map.scrollWheelZoom.enable();
  });
})();
