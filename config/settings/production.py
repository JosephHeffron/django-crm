import os

from django.utils.csp import CSP

from .base import *

DEBUG = False

ALLOWED_HOSTS = [
    host.strip() for host in os.environ["DJANGO_ALLOWED_HOSTS"].split(",") if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# Caddy terminates TLS and proxies to Django over the internal network, so
# Django trusts the X-Forwarded-Proto header from that proxy only.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True

# compose.prod.yml's own healthcheck calls /health/ directly against
# gunicorn (localhost:8000, inside the same container) to check real
# PostgreSQL connectivity — deliberately bypassing Caddy, the same way
# Phase 7's original TCP-connect check did. That request carries no
# X-Forwarded-Proto header (there's no proxy involved), so without this
# exemption SECURE_SSL_REDIRECT would 301 it to https://, which
# gunicorn can't serve itself (it never terminates TLS) — confirmed
# live: the healthcheck's urllib client followed that redirect straight
# into a TLS handshake timeout against a plaintext HTTP server. Safe to
# exempt: no host port is published for `web` in production, so this
# path is never reachable from outside the internal Podman network
# regardless, and the endpoint itself returns nothing more sensitive
# than "ok"/"error".
SECURE_REDIRECT_EXEMPT = [r"^health/$"]

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Content-Security-Policy (docs/PRODUCTION_CONFIG_REVIEW.md #2,
# docs/SECURITY_REVIEW.md #6, closed in Phase 16 — see
# docs/decisions/0007-django-native-csp.md). Deliberately strict, not a
# starting-point-then-loosen policy: this app has zero third-party
# JavaScript, zero external resources (fonts/images/CDNs), and zero
# inline scripts/styles of its own anywhere in templates/ (grep-
# confirmed). The only genuinely dynamic surface is Django's own admin
# interface, which — as of Django 6.1 — ships every one of its own
# script/style tags with {% csp_nonce_attr %} already wired in
# (verified by reading django.contrib.admin's installed templates
# directly, not assumed), so CSP.NONCE here is what makes admin's one
# truly inline <style> block (templates/admin/change_list.html) and
# every admin JS file actually permitted, not 'unsafe-inline'.
#
# Production only, deliberately — Django's own DEBUG=True error page
# (technical_500.html) has inline <script>/<style> with no nonce
# support, so enforcing this in dev too would visibly break the
# traceback page for zero real security benefit (DEBUG is always False
# in production, where this page never renders).
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
    # PWA (Phase 17): default-src 'none' would otherwise block both the
    # web app manifest and the service worker registration.
    "manifest-src": [CSP.SELF],
    "worker-src": [CSP.SELF],
}
