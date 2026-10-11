// Dragging a job to another day on the week and month views
// (Phase 18 unit 4).
//
// This is an enhancement, not the feature. Rescheduling works without
// it through the move controls on the day schedule
// (jobs/_move_actions.html), which are ordinary form fields and work
// on a keyboard and with a screen reader. Nothing here is the only way
// to do anything.
//
// It submits a server-rendered form rather than fetching, because
// CSRF_COOKIE_HTTPONLY is on: no script in this app can read the
// token, so it has to be a field the server wrote.
(function () {
  "use strict";

  var form = document.querySelector("[data-move-form]");
  var startField = form && form.querySelector("[data-move-start]");
  if (!form || !startField) {
    return;
  }

  var dragging = null;

  document.addEventListener("dragstart", function (event) {
    var chip = event.target.closest && event.target.closest("[data-job][draggable]");
    if (!chip) {
      return;
    }
    dragging = chip;
    chip.classList.add("is-dragging");
    // Some browsers refuse the drop without data set.
    if (event.dataTransfer) {
      event.dataTransfer.setData("text/plain", chip.dataset.job);
      event.dataTransfer.effectAllowed = "move";
    }
  });

  document.addEventListener("dragend", function () {
    if (dragging) {
      dragging.classList.remove("is-dragging");
    }
    dragging = null;
    clearTargets();
  });

  function cell(node) {
    return node && node.closest ? node.closest("[data-day]") : null;
  }

  function clearTargets() {
    var marked = document.querySelectorAll(".is-drop-target");
    for (var i = 0; i < marked.length; i += 1) {
      marked[i].classList.remove("is-drop-target");
    }
  }

  document.addEventListener("dragover", function (event) {
    if (!dragging || !cell(event.target)) {
      return;
    }
    // Without this the browser refuses the drop.
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "move";
    }
    clearTargets();
    cell(event.target).classList.add("is-drop-target");
  });

  document.addEventListener("drop", function (event) {
    var target = cell(event.target);
    if (!dragging || !target) {
      return;
    }
    event.preventDefault();

    var day = target.dataset.day; // YYYY-MM-DD
    var wasAt = dragging.dataset.startsAt || ""; // YYYY-MM-DDTHH:MM
    var time = wasAt.indexOf("T") > -1 ? wasAt.split("T")[1] : "09:00";
    if (day + "T" + time === wasAt) {
      // Dropped back where it already was: nothing to do, and a
      // needless write would show up in the change log.
      clearTargets();
      return;
    }

    // The time of day is kept; only the date moves. Dragging across a
    // week grid says nothing about the hour, and guessing would move
    // an 8am job to the middle of the afternoon.
    // The URL comes from the chip, written by Django's url tag. Built
    // here instead, it would keep working right up until the route
    // changed and then fail silently.
    var moveUrl = dragging.dataset.moveUrl;
    if (!moveUrl) {
      clearTargets();
      return;
    }
    startField.value = day + "T" + time;
    form.action = moveUrl;
    form.submit();
  });
})();
