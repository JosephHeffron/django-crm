// The address list follows the chosen customer (Phase 22.5).
//
// Enhancement, not the feature. Without this script the address
// dropdown holds every customer's addresses, each labelled with whose
// it is, and `JobForm.clean` refuses a pair that disagrees — which is
// how the page has always worked and still works with JavaScript off.
//
// What this adds: picking a customer narrows the list to their
// addresses and selects their main one, so the common case needs no
// thought and the uncommon one is a dropdown with two entries instead
// of two hundred.
//
// Options are removed and re-added rather than hidden with CSS, for
// the reason static/js/picker.js gives: an `<option>` with
// `display: none` is honoured by some browsers and ignored by others.
(function () {
  "use strict";

  var pairs = document.querySelectorAll("[data-address-for]");
  Array.prototype.forEach.call(pairs, function (holder) {
    var addresses = document.getElementById(holder.dataset.addressFor);
    var customers = document.getElementById(holder.dataset.addressCustomer);
    if (!addresses || !customers) {
      return;
    }
    var options = Array.prototype.slice.call(addresses.options);
    var note = holder.querySelector("[data-address-note]");

    function belongsTo(option, contactId) {
      return option.dataset.contact === contactId;
    }

    function narrow(pickPrimary) {
      var contactId = customers.value;
      var chosen = addresses.value;
      var theirs = [];

      addresses.textContent = "";
      options.forEach(function (option) {
        // The blank option always stays: an address is optional, and
        // "no address yet" has to remain sayable.
        if (option.value === "") {
          addresses.appendChild(option);
          return;
        }
        if (!contactId || belongsTo(option, contactId)) {
          addresses.appendChild(option);
          theirs.push(option);
        }
      });

      // Keep what was already chosen if it is still in the list;
      // otherwise fall back to their main address, but only when the
      // customer actually changed. Re-selecting silently on every
      // keystroke elsewhere on the page would overwrite a deliberate
      // choice.
      var stillThere = theirs.some(function (option) {
        return option.value === chosen;
      });
      if (stillThere) {
        addresses.value = chosen;
      } else if (pickPrimary) {
        var primary = theirs.filter(function (option) {
          return option.dataset.primary === "1";
        })[0];
        addresses.value = primary ? primary.value : "";
      } else {
        addresses.value = "";
      }

      if (note) {
        if (!contactId) {
          note.textContent = "";
        } else if (theirs.length === 0) {
          note.textContent = "No address on file for them yet.";
        } else if (theirs.length === 1) {
          note.textContent = "Their only address.";
        } else {
          note.textContent = theirs.length + " addresses on file.";
        }
      }
    }

    customers.addEventListener("change", function () {
      narrow(true);
    });
    // On load: narrow to whoever is already chosen, but do not move an
    // address the form arrived with — an edit form and a `?contact=`
    // round trip both land here with a deliberate pair.
    narrow(!addresses.value);
  });
})();
