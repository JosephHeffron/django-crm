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

import time
import unicodedata

from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction

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


# Longer than any username this app will create (Django's field is 150)
# and short enough that the key stays inside the cache table's 255-char
# column. A login POST can carry a megabyte of "username": without this
# the insert fails and a wrong password becomes a 500 (#200).
MAX_USERNAME_KEY = 150


def username_key(username):
    """One bucket per account, however the attempt spelled it.

    **NFKC first, because Django does.** `UsernameField.to_python`
    normalizes the posted value before authenticating, so the fullwidth
    `ｓａｍ` signs in as `sam` — while keying on the raw text gave each
    spelling its own ten-failure budget. A four-letter name with
    fullwidth forms has sixteen variants, so the per-account limit was
    really 160 (#200).

    Then lower-cased: `NewMemberForm` refuses a username differing from
    an existing one only in case, so "Boss" and "boss" are guesses at
    one account. `lower()` rather than `casefold()` deliberately —
    casefold would also fold "ß" into "ss", which Django's
    authentication treats as two different accounts.

    Truncated last, to keep the key inside the cache table's 255-char
    column. Django skips its own normalization above 150 characters, so
    a value that long cannot match an account anyway; this only has to
    count it somewhere.
    """
    normalized = unicodedata.normalize("NFKC", username).strip().lower()
    return f"login-fail-user:{normalized[:MAX_USERNAME_KEY]}"


def _keys(request, username):
    keys = [f"login-fail-ip:{client_ip(request)}"]
    if username:
        keys.append(username_key(username))
    return keys


def _count(key):
    stored = cache.get(key)
    return stored[0] if stored else 0


def refuse(request, username):
    """Has either counter passed the limit?"""
    return any(_count(key) >= MAX_FAILURES for key in _keys(request, username))


def note_failure(request, username, now=None):
    """Count one wrong password against both keys.

    Each entry carries its own **deadline**, and later failures are
    written with only the time left until it. Two reasons, and the
    second one is a bug this had:

    - The window starts at the first failure and is never extended, so
      a steady trickle of guesses cannot keep renewing its own window.
    - `cache.incr()` could not do this. It is a get-then-`set()` with
      no timeout, so every increment rewrote the entry with the cache's
      **default** 300 seconds — the promised fifteen-minute window
      quietly became five after the second failure (#200).
    """
    now = now or time.time()
    for key in _keys(request, username):
        with transaction.atomic():
            _serialize(key)
            stored = cache.get(key)
            if stored is None:
                cache.set(key, (1, now + WINDOW_SECONDS), WINDOW_SECONDS)
                continue
            count, deadline = stored
            remaining = int(deadline - now)
            if remaining <= 0:
                cache.set(key, (1, now + WINDOW_SECONDS), WINDOW_SECONDS)
            else:
                cache.set(key, (count + 1, deadline), remaining)


def _serialize(key):
    """Make concurrent failures on one key take turns.

    Counting is a read and then a write. Without this, two wrong
    passwords landing together in two gunicorn workers both read the
    same count and both write count + 1, and a burst of guesses is
    undercounted (review of #208). A PostgreSQL advisory lock on the
    key, held until the surrounding transaction commits, makes the next
    failure wait and then read the count the last one wrote. The cache
    lives in the same database (ADR 0020), so its read and write sit
    inside the same transaction.

    One key per transaction and never two at once, so two requests can
    never each hold the lock the other is waiting for.

    What this does not close: up to one request per worker can pass
    `refuse()` before an earlier failure is counted, because the
    password check runs in between. With three workers that is a
    handful of attempts past the limit at most, never an unbounded
    stream.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [key])


def forget(request, username):
    """Clear the **username** counter after a successful sign-in.

    Not the IP counter, deliberately. Clearing that let somebody with
    one valid account interleave real sign-ins between guesses at other
    names, resetting the shared per-address count each time and working
    through a list without ever reaching ten on any single username
    (#200). The address counter expires on its own within the window.

    The username counter does clear, so somebody who mistyped four
    times and then got it right is not left most of the way to a
    lockout.
    """
    if username:
        cache.delete(username_key(username))


def forget_username(username):
    """Clear one account's counter without a request.

    The owner setting somebody's password is the recovery path when
    they are locked out (ADR 0021), and a 429 is returned before any
    password is checked — so without this, a new password would not let
    them in until the window expired, which is not what
    `docs/ADMIN_GUIDE.md` promises.
    """
    if username:
        cache.delete(username_key(username))


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
