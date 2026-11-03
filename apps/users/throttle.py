"""Refusing endless password guesses (ADR 0020).

Both login pages share this: `/accounts/login/` and `/admin/login/`.
There is no MFA until Phase 23, so a password is the only thing between
a guesser and the business's records, and `docs/VPS_AUDIT.md` F-SEC-1
and F-PUB-2 recorded that neither page counted attempts at all.

Deliberately not `django-axes`: see the ADR. The counting was never the
hard part — the two things that were actually wrong are both
configuration, and both are fixed elsewhere. This module is what is
left once they are: a counter with a timeout.

**It counts failures, never successes**, under two keys. Per **IP**, so
one machine cannot work through a password list; per **username**, so a
botnet spreading guesses across addresses still trips something. Either
one passing the limit refuses the attempt.
"""

from django.conf import settings
from django.core.cache import cache

# Ten failures in fifteen minutes, per IP and per username. Generous
# for seven people who occasionally mistype, and useless to anybody
# working through a list.
MAX_FAILURES = 10
WINDOW_SECONDS = 15 * 60


def client_ip(request):
    """The address to count against.

    Caddy terminates TLS and proxies to Django, so `REMOTE_ADDR` is the
    proxy for every request and counting it would make one global
    bucket. Caddy **appends** the peer it actually spoke to, so the
    **last** `X-Forwarded-For` entry is the real client even when the
    client sent a header of its own — reading the first entry would let
    anybody pick their own bucket by sending a header, which is worse
    than not counting at all because it looks like it works.

    No proxy in development: the header is absent and `REMOTE_ADDR` is
    the client.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")


def _keys(request, username):
    keys = [f"login-fail-ip:{client_ip(request)}"]
    if username:
        # Lower-cased: Django's own username check is case-insensitive
        # at creation (apps/users/forms.py), so "Boss" and "boss" are
        # guesses at the same account and belong in one bucket.
        keys.append(f"login-fail-user:{username.strip().lower()}")
    return keys


def refuse(request, username):
    """Has either counter passed the limit?"""
    return any((cache.get(key) or 0) >= MAX_FAILURES for key in _keys(request, username))


def note_failure(request, username):
    """Count one wrong password against both keys."""
    for key in _keys(request, username):
        # `add` then `incr`: add() only writes when the key is absent,
        # so the window starts at the first failure and is not extended
        # by later ones — otherwise a steady trickle of guesses would
        # keep renewing its own window and never expire.
        if not cache.add(key, 1, WINDOW_SECONDS):
            try:
                cache.incr(key)
            except ValueError:
                # Expired between the add and the incr. Start again.
                cache.add(key, 1, WINDOW_SECONDS)


def forget(request, username):
    """Clear both counters after a successful sign-in.

    Somebody who mistyped four times and then got it right should not
    be left most of the way to a lockout.
    """
    cache.delete_many(_keys(request, username))


def posted_username(request):
    """What the attempt claimed to be, from either login form.

    Both Django's `AuthenticationForm` and the admin's post the field
    under the `USERNAME_FIELD` name, which is `username` here; read
    from settings rather than hard-coded so a custom user model does
    not silently stop being counted.
    """
    from django.contrib.auth import get_user_model

    field = getattr(get_user_model(), "USERNAME_FIELD", "username")
    return request.POST.get(field, "") or request.POST.get("username", "")


def too_many_response(request):
    """The refusal: HTTP 429, and no hint about the account.

    Says nothing about whether that username exists or whether the
    password was right — a page that distinguished them would answer
    the question the limit exists to stop being asked.
    """
    from django.shortcuts import render

    return render(
        request,
        "registration/too_many_attempts.html",
        {"minutes": WINDOW_SECONDS // 60, "brand": settings.CRM_BRAND_NAME},
        status=429,
    )
