from .base import *

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Mail is printed here, never sent (ADR 0019). No credential is needed
# to develop a flow that sends email, and nothing run on a workstation
# — a test, a seed, a shell session — can reach a real person.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "crm@localhost"
