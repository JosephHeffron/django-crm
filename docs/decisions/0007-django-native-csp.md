# 0007 — Content-Security-Policy via Django's built-in middleware, not Caddy

## Context

`docs/SECURITY_REVIEW.md` #6 (Phase 6) and `docs/PRODUCTION_CONFIG_REVIEW.md`
#2 (Phase 8) both deferred adding a CSP header, reasoning that Caddy
(once it existed) would be "the natural place for it" — Django itself
had "no first-class built-in for this (would need `django-csp` or
hand-rolled middleware)" at the time those findings were written. Both
also flagged the same real blocker: Django's built-in admin interface
(actively used, `apps/crm/admin.py` registers all six models) has
inline `<script>`/`<style>` content whose interaction with a strict CSP
"can only be reliably confirmed by watching a real browser's console
for CSP violations" — something neither prior review's available
tooling (`curl`, HTTP-status-only checks) could do.

Phase 16 revisits this with two things that changed since those
findings were written:

1. This project's actual installed Django version is 6.1.1, which — as
   discovered while starting this phase, not assumed — ships genuine
   first-class CSP support: `django.middleware.csp.
   ContentSecurityPolicyMiddleware`, `SECURE_CSP`/
   `SECURE_CSP_REPORT_ONLY` settings, per-request nonces
   (`django.utils.csp.LazyNonce`), and a `{% csp_nonce_attr %}`
   template tag. Reading Django's own installed admin templates
   directly (not assumed from documentation) confirmed every single
   `<script>`/`<style>` tag across every admin template already carries
   `{% csp_nonce_attr %}` — Django's own admin ships CSP-ready out of
   the box on this version, with the caveat that a `csp` context
   processor must be added for the nonce to actually render (without
   it, `{% csp_nonce_attr %}` silently renders nothing).
2. A real browser check, the specific thing both prior findings said
   was missing, became possible this session via a headless Chromium
   (Playwright) instance — not interactive computer-use tooling, but a
   genuine browser engine loading real pages and exposing its actual
   console, which is what those findings actually asked for.

## Alternatives considered

- **A CSP header set by Caddy** (the plan both prior findings
  assumed). Rejected now that Django's own native support exists:
  Caddy would have to either apply one static policy with no
  per-request nonce (forcing `'unsafe-inline'` for admin's genuinely
  inline `<style>` block, since Caddy can't generate/inject a matching
  per-response nonce into Django's own rendered HTML), or duplicate a
  meaningful amount of Django-side logic to stay in sync. Django's
  native middleware does this correctly for free, already installed,
  no new dependency.
- **`django-csp`** (the third-party package, the other option both
  prior findings named). Rejected: redundant with Django 6.1's own
  built-in equivalent — adding a second CSP mechanism would be exactly
  the kind of unnecessary dependency `CLAUDE.md`'s complexity rule asks
  to avoid.
- **`'unsafe-inline'` for `script-src`/`style-src`** as a lower-effort
  policy that wouldn't need nonce plumbing at all. Rejected: this
  defeats CSP's actual point (an XSS payload injected as inline script
  would execute exactly the same as legitimate inline content) for a
  project that, per the live verification below, doesn't need it —
  every genuinely inline tag in Django admin already carries a nonce
  attribute ready to use.
- **Report-Only mode first** (`SECURE_CSP_REPORT_ONLY`, no enforcement)
  as a lower-risk rollout. Rejected as unnecessary given the live
  verification below found zero violations under full enforcement —
  shipping Report-Only first would just be an extra step with no real
  data to gather that this phase's own testing didn't already gather
  directly.

## Decision

CSP is implemented via Django's own `django.middleware.csp.
ContentSecurityPolicyMiddleware` (added to `MIDDLEWARE` in
`config/settings/base.py`, immediately after `SecurityMiddleware`) plus
`django.template.context_processors.csp` (added to `TEMPLATES`, also in
`base.py`, so `{% csp_nonce_attr %}` renders a real nonce rather than
nothing). The actual policy (`SECURE_CSP`) is defined only in
`config/settings/production.py`:

```python
SECURE_CSP = {
    "default-src": [CSP.NONE],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF, CSP.NONCE],
    "img-src": [CSP.SELF],
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "base-uri": [CSP.NONE],
    "object-src": [CSP.NONE],
}
```

Deliberately production-only, not `base.py` (i.e. not enforced under
`DEBUG=True`): Django's own `DEBUG=True` error page
(`django/views/templates/technical_500.html`) has inline
`<script>`/`<style>` with no nonce support, so enforcing this in dev
too would visibly break the traceback page for zero real security
benefit — that page never renders in production, where `DEBUG` is
always `False`.

## Live verification

Confirmed live with a headless Chromium instance (Playwright, installed
into an isolated throwaway venv for this session only — not a project
dependency), against a real `manage.py runserver` running under
`config/settings/production.py` (`SECURE_SSL_REDIRECT` locally
overridden to `False` purely so plain HTTP `runserver` could serve the
request at all; every other production setting, including `SECURE_CSP`
itself, applied unmodified) with `--insecure` so static files serve
under `DEBUG=False`, matching real production's static-file behavior
closely enough for this specific check (Caddy serves `/static/*`
directly in real production, per `docs/ARCHITECTURE.md`, but the same
`X-Content-Type-Options: nosniff`/CSP-relevant response headers this
check cares about come from Django's `SecurityMiddleware`/CSP
middleware either way).

Exercised: admin login, the admin index, a changelist page (Companies,
including its sidebar filters and theme toggle), an add form (Deal —
date-picker/calendar/clock widgets, prepopulated-fields JS, related-
object dropdown widgets), and a related-object "add" popup (opening a
real second browser tab/page, adding a Company inline from the Deal
form). A console listener captured every browser console message across
all of these; **zero Content-Security-Policy violations, zero other
console errors**. A full-page screenshot of the add-form additionally
confirmed correct visual rendering (icons, widgets, layout), not just
an absence of console errors.

Confirmed via `curl` that the response actually carries the intended
header with a real per-request nonce:
```
Content-Security-Policy: default-src 'none'; script-src 'self' 'nonce-<...>'; style-src 'self' 'nonce-<...>'; img-src 'self'; font-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'
```

**A real gap this same verification caught**: this project's own custom
`templates/500.html` had a genuinely inline `<style>` block, un-nonced
— Sourcery's review of the first version of this change (PR #88) caught
it; my own earlier check of this project's templates had only grepped
for `<script`, not `<style>`. Worse, a nonce-based fix wasn't even
viable here: `django.views.defaults.server_error` (Django's default
`handler500`) renders `500.html` with no context at all (`Context:
None`, per that view's own docstring — confirmed by calling
`loader.get_template("500.html").render()` directly, no request
argument, the same way that view does), so `{% csp_nonce_attr %}`
would have rendered nothing regardless. Fixed by moving the CSS to a
static file (`static/css/error.css`) and linking it as an external,
same-origin stylesheet instead — `style-src 'self'` permits that with
no nonce needed, sidestepping the missing-context problem entirely
rather than writing a custom `handler500` just to fix one CSS rule.
Re-verified live: deliberately triggered a real 500 (a temporary test
route raising an exception, never committed) under full CSP
enforcement, confirmed via the browser's own computed style
(`getComputedStyle(document.body).maxWidth` reporting the expected
`512px`, i.e. `32rem`) that the stylesheet genuinely applied, not just
loaded with a 200 — and confirmed zero CSP violations on that response.

## Reason

Closes `docs/SECURITY_REVIEW.md` #6 and `docs/PRODUCTION_CONFIG_REVIEW.md`
#2 with the specific evidence both originally said was missing — a
real browser's console, not an assumption about how CSP and Django
admin's inline content would interact. The resulting policy is
genuinely strict (`default-src 'none'`, no `'unsafe-inline'` anywhere)
because this app's actual surface (zero third-party JS, zero external
resources, and — as of Django 6.1 — an admin interface that already
ships nonce-ready) supports that without a fallback compromise.

## Consequences

- Any future *project-authored* template that adds a genuinely inline
  `<script>`/`<style>` block will need `{% csp_nonce_attr %}` on it
  (the same mechanism admin already uses) or it will be silently
  blocked in production — worth flagging in `docs/DEVELOPER_GUIDE.md`
  so a future contributor doesn't lose time to an invisible CSP block
  with no HTTP-visible symptom.
- If a future feature genuinely needs an external resource (a CDN
  font, a third-party embed), the relevant `SECURE_CSP` directive needs
  a deliberate addition — `default-src 'none'` means anything not
  explicitly listed is blocked by default, which is the intended
  fail-closed behavior, not a bug to work around by weakening the
  policy generally.
- No change needed to `Caddyfile`/`Caddyfile.dev` — CSP applies to
  every Django-rendered HTML response regardless of proxy layer;
  static/media files Caddy serves directly were already confirmed
  (Phase 8) not to need it, since CSP only governs how an HTML document
  behaves, not how a `.css`/`.js` asset response itself is treated.

## Date

2026-09-28
