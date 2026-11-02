from .base import *

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Nothing in this app sends mail (ADR 0021), and production configures
# no backend at all. This stays as a guard rather than a feature: if any
# future code calls send_mail on a workstation, it prints instead of
# reaching a real person — a test, a seed or a shell session included.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "crm@localhost"
