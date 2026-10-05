"""
Shared Django settings for the CRM.

Environment-specific settings live in development.py and production.py,
which both import everything from this module and override only what
differs. Nothing environment-specific belongs here.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = False

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.users",
    "apps.crm",
    "apps.jobs",
    "apps.messaging",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Sets request._csp_nonce (lazy — only generated if a template
    # actually reads it via {% csp_nonce_attr %}) and, on the way out,
    # the Content-Security-Policy header from SECURE_CSP
    # (config/settings/production.py; empty/no-op in dev — see that
    # file for the policy and docs/decisions/0007-django-native-csp.md
    # for why this project uses Django's own CSP middleware rather than
    # adding it at the Caddy layer, the plan docs/SECURITY_REVIEW.md/
    # docs/PRODUCTION_CONFIG_REVIEW.md originally assumed).
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Loads the business settings (name, logo, currency) once per request.
    "apps.core.business.BusinessSettingsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Required for {% csp_nonce_attr %} (used throughout
                # Django's own admin templates) to render a real nonce
                # rather than nothing — without this, admin's one
                # genuinely inline <style> block (the changelist
                # column-width block in templates/admin/change_list.html)
                # would have no nonce to match SECURE_CSP's style-src
                # policy against, and a strict CSP would silently block
                # it in a real browser with no HTTP-visible symptom.
                "django.template.context_processors.csp",
                # Brand name + role-filtered navigation (ADR 0008).
                "apps.core.context_processors.app_shell",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        # Django's own default is 8 — raised per docs/SECURITY_REVIEW.md
        # to a more modern minimum. No downside: this only affects
        # future password sets/changes, not existing accounts.
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# No JavaScript in this app ever reads the CSRF cookie — every
# {% csrf_token %} is a server-rendered hidden form field — so there's
# no reason for the cookie to be script-readable. See
# docs/SECURITY_REVIEW.md.
CSRF_COOKIE_HTTPONLY = True

LANGUAGE_CODE = "en-us"
# The business's local timezone — "today's jobs", daily revenue, and
# follow-up due dates are all local-day concepts. Stored datetimes stay
# UTC (USE_TZ below); this only governs display and date boundaries.
TIME_ZONE = os.environ.get("CRM_TIME_ZONE", "America/New_York")

# Shown in the app header, page titles, and the PWA manifest. The short
# name is what a phone shows under the home-screen icon (~12 chars max).
CRM_BRAND_NAME = os.environ.get("CRM_BRAND_NAME", "Exterior CRM")
CRM_BRAND_SHORT_NAME = os.environ.get("CRM_BRAND_SHORT_NAME", CRM_BRAND_NAME[:12])
# Where the sidebar's "Ideas" / "Report a bug" links and the help button
# send people (a mailto: link). Empty hides them. Set in .env — never
# hard-code an address in this public repository.
CRM_SUPPORT_EMAIL = os.environ.get("CRM_SUPPORT_EMAIL", "").strip()
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "users:login"
LOGIN_REDIRECT_URL = "core:index"
LOGOUT_REDIRECT_URL = "users:login"

# Without this, Django's own default logging config (django.utils.log.
# DEFAULT_LOGGING) gates its only console handler behind DEBUG=True —
# meaning in production (DEBUG=False), an unhandled view exception
# logs literally nowhere: not to console/journald, not anywhere,
# since ADMINS/EMAIL_* are also unset here (mail_admins, the only
# production-active handler DEFAULT_LOGGING defines, is a silent
# no-op without them). Confirmed live (see docs/LOGGING_REVIEW.md):
# simulating Django's own django.request.error(..., exc_info=True) —
# exactly what happens on every unhandled view exception — produced
# zero output under production settings before this fix.
#
# "django" gets its own explicit, unconditional console handler
# (not gated by any DEBUG filter) with propagate=False, so it isn't
# also picked up by the root logger below — verified live that
# without propagate=False, a django.request error printed twice under
# DEBUG=True (once via this handler, once via root). Everything else
# (this project's own loggers, e.g. apps/core/views.py's health-check
# failure log) has no handler of its own, so it reaches the root
# logger's console handler by Python logging's normal propagation.
#
# Deliberately just a StreamHandler with no custom Formatter or file
# handler — journald (via the container runtime) already timestamps
# and persists everything this container prints to stdout, matching
# how every other piece of this stack's logs (gunicorn, Caddy,
# PostgreSQL) already reach an operator; adding a second log-shipping
# mechanism here would just be redundant infrastructure.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
