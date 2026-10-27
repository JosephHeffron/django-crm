// "Tick everyone on this page" for the customer and task lists
// (Phase 22).
//
// An enhancement, not the feature. The bulk action bar is an ordinary
// form: the row checkboxes, the action dropdown and the Apply button
// are all server-rendered fields that work on a keyboard, with a
// screen reader, and with this file blocked. All this does is save
// twenty-five clicks.
//
// The header checkbox is therefore written `hidden` in the template
// and revealed here. A control that does nothing without JavaScript
// should not be on the page when there is none.
(function () {
  "use strict";

  var all = document.querySelector("[data-check-all]");
  if (!all) {
    return;
  }

  var form = all.closest("form");
  var boxes = form ? form.querySelectorAll("input[name='selected']") : [];
  if (!boxes.length) {
    return;
  }

  function everyOneTicked() {
    for (var i = 0; i < boxes.length; i++) {
      if (!boxes[i].checked) {
        return false;
      }
    }
    return true;
  }

  all.hidden = false;
  all.checked = false;

  all.addEventListener("change", function () {
    for (var i = 0; i < boxes.length; i++) {
      boxes[i].checked = all.checked;
    }
  });

  // Untick the header once a row is unticked, so it never claims the
  // whole page is selected when it isn't.
  for (var i = 0; i < boxes.length; i++) {
    boxes[i].addEventListener("change", function () {
      all.checked = everyOneTicked();
    });
  }
})();
