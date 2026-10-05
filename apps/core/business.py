"""The business settings for the current request.

BusinessSettingsMiddleware loads the settings row once per request and
makes it available two ways: ``request.business`` for views and the
context processor, and a context variable for code with no request at
hand — the ``money`` template filter, which needs the currency symbol on
every page. Outside a request (management commands, plain unit tests)
the symbol falls back to "$" without touching the database.
"""

from contextvars import ContextVar

from .models import BusinessSettings

_current = ContextVar("business_settings", default=None)


def currency_symbol():
    business = _current.get()
    return business.currency_symbol if business is not None else "$"


class BusinessSettingsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.business = BusinessSettings.load()
        token = _current.set(request.business)
        try:
            return self.get_response(request)
        finally:
            _current.reset(token)
