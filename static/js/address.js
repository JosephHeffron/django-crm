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

    // "New address" opens its own page with the customer pre-filled,
    // via `?contact=` — but the server could only know whoever was
    // chosen when the page was built. Picking somebody else and then
    // clicking it opened the address form for the wrong customer, or
    // for nobody (#202).
    function pointNewAddressAt(contactId) {
      var link = holder.parentElement
        ? holder.parentElement.querySelector("[data-new-address]")
        : null;
      if (!link) {
        return;
      }
      var url = new URL(link.href, window.location.origin);
      if (contactId) {
        url.searchParams.set("contact", contactId);
      } else {
        url.searchParams.delete("contact");
      }
      link.href = url.pathname + "?" + url.searchParams.toString();
    }

    function narrow(pickPrimary) {
      var contactId = customers.value;
      var chosen = addresses.value;
      var theirs = [];
      // No customer chosen means no address, and the list goes back
      // to everything the server sent. Two bugs lived here (#202):
      // treating an empty id as "matches everybody" let the primary
      // search below pick the first primary in the list — somebody
      // else's house — and keeping the previous selection left an
      // address attached to nobody, which only the server's own check
      // would have caught, on submit.
      if (!contactId) {
        pickPrimary = false;
        chosen = "";
      }

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
      // Changing the customer is an explicit act, so this is the one
      // moment it is right to choose an address for somebody.
      narrow(true);
      pointNewAddressAt(customers.value);
    });

    // On load, **never** choose. A job or estimate saved with no
    // address renders an empty field, and filling in the primary here
    // meant saving an unrelated field later persisted an address
    // nobody picked (#202). The same applies after a validation error
    // re-renders a form where the address was deliberately cleared.
    //
    // The `?contact=` round trip is already handled: the server picks
    // the primary in get_initial, so the field arrives filled and this
    // only has to narrow the list around it.
    narrow(false);
    pointNewAddressAt(customers.value);
  });
})();
