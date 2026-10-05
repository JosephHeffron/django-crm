"""Turning an address into a point on the map (Phase 17.5 step 8,
ADR 0011).

Lookups go to OpenStreetMap's Nominatim service, **from the server, one
at a time, at most one per second**, with a User-Agent that says who we
are — that is Nominatim's usage policy, and ignoring it gets an IP
blocked. The result is stored on the property, so an address is sent
once rather than on every page view.

Nothing calls this while rendering a page. The map page lists what still
needs placing and the Owner asks for it, or
`manage.py locate_properties` does a batch; either way a slow or
unavailable service delays nobody's page.

What's sent is the service address and nothing else: no customer name,
no phone number, no job.
"""

import json
import logging
import time
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

ENDPOINT = "https://nominatim.openstreetmap.org/search"
# Nominatim asks for no more than one request a second from one source.
MIN_SECONDS_BETWEEN = 1.0
TIMEOUT_SECONDS = 10

_last_call = 0.0


class LookupError_(Exception):
    """The service couldn't be reached, or answered with something we
    don't understand. Not finding an address is not this — that's a
    plain None."""


def user_agent():
    """Nominatim requires a real contact. The support address is already
    configured for the app's footer links."""
    contact = getattr(settings, "CRM_SUPPORT_EMAIL", "") or "unknown"
    return f"{settings.CRM_BRAND_NAME} CRM (self-hosted; {contact})"


def _wait_turn():
    """Hold to one request per second, however often we're called."""
    global _last_call
    gap = time.monotonic() - _last_call
    if gap < MIN_SECONDS_BETWEEN:
        time.sleep(MIN_SECONDS_BETWEEN - gap)
    _last_call = time.monotonic()


def lookup(address, *, opener=None):
    """(latitude, longitude) for an address, or None when Nominatim has
    never heard of it. Raises LookupError_ if the service itself is the
    problem, so "we couldn't ask" is never mistaken for "it isn't
    there"."""
    # Resolved here, not bound as a default argument: a default is
    # captured when the function is defined, so patching this module's
    # `urlopen` wouldn't take — and a test that thinks it has stubbed
    # the network would quietly call the real service.
    send = opener or urlopen
    query = urlencode({"q": address, "format": "jsonv2", "limit": 1})
    request = Request(f"{ENDPOINT}?{query}", headers={"User-Agent": user_agent()})
    _wait_turn()
    try:
        with send(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as error:  # network, timeout, bad JSON — all the same here
        raise LookupError_(str(error)) from error
    if not payload:
        return None
    try:
        first = payload[0]
        return Decimal(str(first["lat"])), Decimal(str(first["lon"]))
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise LookupError_("Nominatim replied with something unexpected") from error


def locate(service_property, *, opener=None):
    """Place one property. Returns "located", "not found", or raises
    LookupError_. Saves the address it was placed from, so editing the
    address re-opens the lookup."""
    address = str(service_property)
    found = lookup(address, opener=opener)
    if found is None:
        return "not found"
    service_property.latitude, service_property.longitude = found
    service_property.located_at = timezone.now()
    service_property.located_address = address[:400]
    service_property.save(update_fields=["latitude", "longitude", "located_at", "located_address"])
    return "located"


def place_by_hand(service_property, latitude, longitude):
    """Drop a pin where the Owner says, for an address Nominatim can't
    find or one they'd rather not send."""
    service_property.latitude = Decimal(str(latitude))
    service_property.longitude = Decimal(str(longitude))
    service_property.located_at = timezone.now()
    service_property.located_address = str(service_property)[:400]
    service_property.save(update_fields=["latitude", "longitude", "located_at", "located_address"])
