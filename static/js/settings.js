// Business Settings page (Phase 17.5 step 3). Progressive enhancement:
// without this script one blank link row is always offered and a new
// logo is center-cropped by the server (apps/core/branding.py).
(function () {
  "use strict";

  // ---------- "Add link": clone the formset's empty row ----------

  var addLink = document.querySelector("[data-add-link]");
  var rows = document.querySelector("[data-link-rows]");
  var template = document.querySelector("[data-link-template]");
  var total = document.getElementById("id_links-TOTAL_FORMS");
  if (addLink && rows && template && total) {
    addLink.addEventListener("click", function () {
      var index = parseInt(total.value, 10);
      var html = template.innerHTML.replace(/__prefix__/g, String(index));
      var holder = document.createElement("div");
      holder.innerHTML = html; // our own server-rendered template, no user data
      var row = holder.firstElementChild;
      rows.appendChild(row);
      total.value = String(index + 1);
      var first = row.querySelector("select, input");
      if (first) {
        first.focus();
      }
    });
  }

  // ---------- Logo crop ----------

  var input = document.querySelector("[data-logo-input]");
  var dialog = document.querySelector("[data-crop-dialog]");
  if (!input || !dialog || typeof window.createImageBitmap !== "function" || typeof dialog.showModal !== "function") {
    return;
  }
  var canvas = dialog.querySelector("[data-crop-canvas]");
  var zoom = dialog.querySelector("[data-crop-zoom]");
  var ctx = canvas.getContext("2d");
  var preview = document.querySelector("[data-logo-canvas]");
  var previewBox = document.querySelector("[data-logo-preview]");
  var filename = document.querySelector("[data-logo-filename]");
  var fields = {
    x: document.getElementById("id_crop_x"),
    y: document.getElementById("id_crop_y"),
    size: document.getElementById("id_crop_size"),
  };
  var MAX_BYTES = 5 * 1024 * 1024;
  var bitmap = null;
  var scale = 1;
  var offsetX = 0;
  var offsetY = 0;
  var crop = { x: 0, y: 0, size: 0 };
  var drag = null;

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function keepInside() {
    crop.size = clamp(crop.size, 16, Math.min(bitmap.width, bitmap.height));
    crop.x = clamp(crop.x, 0, bitmap.width - crop.size);
    crop.y = clamp(crop.y, 0, bitmap.height - crop.size);
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, offsetX, offsetY, bitmap.width * scale, bitmap.height * scale);
    var sx = offsetX + crop.x * scale;
    var sy = offsetY + crop.y * scale;
    var ss = crop.size * scale;
    ctx.beginPath();
    ctx.rect(0, 0, canvas.width, canvas.height);
    ctx.rect(sx, sy, ss, ss);
    ctx.fillStyle = "rgba(15, 23, 42, 0.55)";
    ctx.fill("evenodd");
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    ctx.strokeRect(sx, sy, ss, ss);
  }

  function reset(message) {
    input.value = "";
    fields.x.value = "";
    fields.y.value = "";
    fields.size.value = "";
    filename.textContent = message || "";
  }

  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file) {
      return;
    }
    if (file.size > MAX_BYTES) {
      reset("That file is over 5 MB. Choose a smaller image.");
      return;
    }
    createImageBitmap(file).then(
      function (image) {
        bitmap = image;
        scale = Math.min(canvas.width / bitmap.width, canvas.height / bitmap.height);
        offsetX = (canvas.width - bitmap.width * scale) / 2;
        offsetY = (canvas.height - bitmap.height * scale) / 2;
        var side = Math.min(bitmap.width, bitmap.height);
        crop = { x: (bitmap.width - side) / 2, y: (bitmap.height - side) / 2, size: side };
        zoom.value = "100";
        draw();
        dialog.showModal();
        canvas.focus();
      },
      function () {
        reset("That file isn't an image this browser can read.");
      }
    );
  });

  zoom.addEventListener("input", function () {
    var centerX = crop.x + crop.size / 2;
    var centerY = crop.y + crop.size / 2;
    crop.size = (Math.min(bitmap.width, bitmap.height) * parseInt(zoom.value, 10)) / 100;
    crop.x = centerX - crop.size / 2;
    crop.y = centerY - crop.size / 2;
    keepInside();
    draw();
  });

  canvas.tabIndex = 0;
  canvas.addEventListener("pointerdown", function (event) {
    drag = { x: event.clientX, y: event.clientY, cropX: crop.x, cropY: crop.y };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", function (event) {
    if (!drag) {
      return;
    }
    crop.x = drag.cropX + (event.clientX - drag.x) / scale;
    crop.y = drag.cropY + (event.clientY - drag.y) / scale;
    keepInside();
    draw();
  });
  canvas.addEventListener("pointerup", function () {
    drag = null;
  });
  canvas.addEventListener("keydown", function (event) {
    var step = (event.shiftKey ? 40 : 8) / scale;
    var moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (moves[event.key]) {
      event.preventDefault();
      crop.x += moves[event.key][0];
      crop.y += moves[event.key][1];
      keepInside();
      draw();
    }
  });

  dialog.querySelector("[data-crop-apply]").addEventListener("click", function () {
    fields.x.value = String(Math.round(crop.x));
    fields.y.value = String(Math.round(crop.y));
    fields.size.value = String(Math.floor(crop.size));
    var pctx = preview.getContext("2d");
    pctx.clearRect(0, 0, preview.width, preview.height);
    pctx.drawImage(bitmap, crop.x, crop.y, crop.size, crop.size, 0, 0, preview.width, preview.height);
    Array.prototype.forEach.call(previewBox.children, function (child) {
      child.hidden = child !== preview;
    });
    filename.textContent = input.files[0].name + " — click Save changes to use it.";
    dialog.close();
  });

  dialog.querySelector("[data-crop-cancel]").addEventListener("click", function () {
    reset("");
    dialog.close();
  });
  dialog.addEventListener("cancel", function () {
    reset("");
  });
})();
