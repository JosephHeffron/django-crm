"""Progressive Web App support: manifest data, service-worker precache
list, and a content-derived cache version.

The service worker precaches only the static app shell and an offline
page — never authenticated HTML, since crews share phones (Phase 17 plan).
"""

import hashlib
from functools import lru_cache

from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

# Static files the service worker keeps available offline.
PRECACHE_STATIC = (
    "css/tokens.css",
    "css/base.css",
    "js/nav.js",
    "js/ui.js",
    "fonts/inter/inter-latin-wght-normal.woff2",
    "js/sw-register.js",
    "pwa/icons/icon.svg",
    "pwa/icons/icon-192.png",
    "pwa/icons/icon-512.png",
    "pwa/icons/apple-touch-icon.png",
)

THEME_COLOR = "#2563eb"
BACKGROUND_COLOR = "#f3f4f6"


def precache_urls():
    return [static(path) for path in PRECACHE_STATIC]


def _compute_asset_version():
    digest = hashlib.sha256()
    for path in PRECACHE_STATIC:
        found = finders.find(path)
        if found:
            with open(found, "rb") as handle:
                digest.update(handle.read())
    # The offline page's markup ships in the SW cache too, so a brand
    # rename must also roll the cache.
    digest.update(settings.CRM_BRAND_NAME.encode())
    return digest.hexdigest()[:16]


_cached_asset_version = lru_cache(maxsize=1)(_compute_asset_version)


def asset_version():
    """Same value in every gunicorn worker (derived from file contents,
    not startup time), so browsers don't see a "new" service worker on
    every request that lands on a different worker. Recomputed on every
    call under DEBUG so a CSS edit shows up without a server restart."""
    if settings.DEBUG:
        return _compute_asset_version()
    return _cached_asset_version()


def manifest(business_name=""):
    """The web app manifest; a business name set in Business Settings
    replaces the CRM_BRAND_NAME default."""
    return {
        "id": "/",
        "name": business_name or settings.CRM_BRAND_NAME,
        "short_name": business_name[:12] if business_name else settings.CRM_BRAND_SHORT_NAME,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": BACKGROUND_COLOR,
        "theme_color": THEME_COLOR,
        "icons": [
            {"src": static("pwa/icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("pwa/icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {
                "src": static("pwa/icons/icon-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }
