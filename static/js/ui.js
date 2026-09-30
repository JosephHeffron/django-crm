// Small shared behaviors (Phase 17.5). Progressive enhancement: each
// one has a no-JS fallback in the markup.
(function () {
  "use strict";

  // <select data-autosubmit> submits its form on change (the markup
  // carries a <noscript> submit button for no-JS use).
  document.addEventListener("change", function (event) {
    var target = event.target;
    if (target.matches && target.matches("select[data-autosubmit]") && target.form) {
      target.form.submit();
    }
  });
})();
