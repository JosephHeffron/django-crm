"""Coming back to where you were (Phase 18.5 unit 3).

Several pages hand each other a `next` so the user lands back where
they started: marking a task complete, dismissing a notification, and
now adding a customer or address from the middle of booking a job.

A `next` is attacker-controlled — it arrives in a URL anyone can
compose and send — so it is checked against this host every time rather
than followed as given. That is Django's own check, not a hand-rolled
one; a hand-rolled version of exactly this was the open redirect found
in Phase 17.5 step 4.
"""

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request, fallback="", param="next"):
    """The `next` this request asked for, or `fallback`.

    Looked for in the submitted data first and the query string second,
    so one helper serves a form post and a link.
    """
    target = request.POST.get(param) or request.GET.get(param) or ""
    if not target:
        return fallback
    allowed = url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    )
    return target if allowed else fallback


def with_params(url, **params):
    """`url` with these query values set, replacing any already there.

    Used to hand a newly created record back to the form that asked for
    it, without caring what the form already had in its query string —
    appending blindly would give two `contact=` values and let the
    wrong one win.
    """
    parts = urlparse(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in params
    ]
    query.extend((key, str(value)) for key, value in params.items() if value is not None)
    return urlunparse(parts._replace(query=urlencode(query)))
