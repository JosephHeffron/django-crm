import os

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
