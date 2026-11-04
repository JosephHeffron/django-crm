"""Refusing endless password guesses (ADR 0020).

There is no MFA until Phase 23 and unit 3 puts this app on the public
internet, so a password is the only thing between a guesser and the
business's records. `docs/VPS_AUDIT.md` F-SEC-1 and F-PUB-2 recorded
that neither login page counted attempts.

Two of these tests exist for the things that were *actually* wrong,
neither of which is the counting: the cache has to be shared across
gunicorn's workers, and the client IP has to be the client's.
"""

import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.users import throttle

User = get_user_model()

PASSWORD = "correct-horse-battery"
LOGIN = reverse("users:login")
ADMIN_LOGIN = "/admin/login/"


def _row_expiry(key):
    """When the database cache will actually drop this entry.

    Straight from the table, because that is the thing the fifteen
    minutes is a promise about. Django prefixes stored keys with its
    key prefix and version, hence the LIKE.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT expires FROM crm_cache WHERE cache_key LIKE %s", [f"%{key}"])
        row = cursor.fetchone()
    assert row, f"no cache row for {key}"
    return row[0]


def _a_request():
    """A bare request for the counting helpers, which only read the
    address off it."""
    from django.test import RequestFactory

    return RequestFactory().post(LOGIN, {})


class RateLimitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sam", password=PASSWORD)
        cache.clear()

    def guess(self, url=LOGIN, username="sam", password="wrong-password", **extra):
        return self.client.post(url, {"username": username, "password": password}, **extra)

    def test_the_limit_trips_after_ten_failures(self):
        for attempt in range(throttle.MAX_FAILURES):
            response = self.guess()
            self.assertEqual(response.status_code, 200, f"attempt {attempt + 1}")

        refused = self.guess()
        self.assertEqual(refused.status_code, 429)
        self.assertContains(refused, "Too many sign-in attempts", status_code=429)

    def test_the_right_password_is_refused_once_the_limit_trips(self):
        """The point of the limit: being right at guess eleven does not
        help, or a list would simply be worked through."""
        for _ in range(throttle.MAX_FAILURES):
            self.guess()
        self.assertEqual(self.guess(password=PASSWORD).status_code, 429)
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_a_correct_password_after_a_few_failures_still_works(self):
        """Mistyping is normal. Four wrong then right must sign in, and
        must leave nothing behind."""
        for _ in range(4):
            self.guess()
        response = self.guess(password=PASSWORD)
        self.assertRedirects(response, reverse("core:index"))
        # Their username's count clears. The address count does not,
        # deliberately: clearing it let one valid account reset the
        # shared bucket between guesses at other names (#200). It
        # expires on its own inside the window.
        self.assertEqual(throttle._count("login-fail-user:sam"), 0)
        self.assertEqual(throttle._count("login-fail-ip:127.0.0.1"), 4)

    def test_the_refusal_says_nothing_about_the_account(self):
        """A page that distinguished "no such user" from "wrong
        password" would answer the question the limit exists to stop
        being asked."""
        for _ in range(throttle.MAX_FAILURES):
            self.guess(username="nobody-at-all")
        refused = self.guess(username="nobody-at-all")
        body = refused.content.decode().lower()
        self.assertEqual(refused.status_code, 429)
        self.assertNotIn("nobody-at-all", body)
        self.assertNotIn("does not exist", body)
        self.assertNotIn("incorrect", body)

    def test_one_username_guessed_from_many_addresses_still_trips(self):
        """The per-username counter, which is what a botnet spreading
        guesses across addresses runs into. Each request arrives from a
        different client, so the per-IP counter never reaches two.
        """
        for attempt in range(throttle.MAX_FAILURES):
            self.guess(HTTP_X_FORWARDED_FOR=f"10.0.0.{attempt + 1}")
        refused = self.guess(HTTP_X_FORWARDED_FOR="10.0.0.99")
        self.assertEqual(refused.status_code, 429)

    def test_one_address_guessing_many_usernames_still_trips(self):
        """And the per-IP counter, which is what one machine working
        through a list of names runs into. No username repeats, so the
        per-username counter never reaches two.
        """
        for attempt in range(throttle.MAX_FAILURES):
            self.guess(username=f"someone{attempt}")
        self.assertEqual(self.guess(username="someone-else").status_code, 429)

    def test_a_locked_out_username_does_not_lock_out_everybody(self):
        """Somebody guessing at "sam" from one address must not stop
        another person signing in from their own."""
        for _ in range(throttle.MAX_FAILURES):
            self.guess(HTTP_X_FORWARDED_FOR="10.0.0.1")
        User.objects.create_user("riley", password=PASSWORD)
        response = self.client.post(
            LOGIN,
            {"username": "riley", "password": PASSWORD},
            HTTP_X_FORWARDED_FOR="10.0.0.2",
        )
        self.assertRedirects(response, reverse("core:index"))

    def test_the_admin_login_is_limited_by_the_same_counters(self):
        """An attacker choosing the other page must gain nothing: five
        failures on each page is ten."""
        for _ in range(5):
            self.guess()
        for _ in range(5):
            self.guess(url=ADMIN_LOGIN)
        self.assertEqual(self.guess(url=ADMIN_LOGIN).status_code, 429)
        self.assertEqual(self.guess().status_code, 429)

    def test_the_admin_login_page_still_works(self):
        """The limit must not have broken the page it guards: the route
        is declared before admin/ and has to behave like the admin's
        own.
        """
        self.assertEqual(self.client.get(ADMIN_LOGIN).status_code, 200)
        self.assertEqual(reverse("admin:login"), ADMIN_LOGIN)

        staff = User.objects.create_user("admin", password=PASSWORD, is_staff=True)
        staff.is_superuser = True
        staff.save(update_fields=["is_superuser"])
        response = self.client.post(
            ADMIN_LOGIN, {"username": "admin", "password": PASSWORD, "next": "/admin/"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.client.session.get("_auth_user_id"))


class ThingsFoundInReviewTests(TestCase):
    """Four ways this was wrong when first written (#200)."""

    def setUp(self):
        self.user = User.objects.create_user("sam", password=PASSWORD)
        cache.clear()

    def guess(self, **extra):
        return self.client.post(LOGIN, {"username": "sam", "password": "wrong-password"}, **extra)

    def test_the_window_is_fifteen_minutes_not_the_cache_default(self):
        """`cache.incr()` is a get-then-set with no timeout, so every
        increment rewrote the entry with the cache's default 300
        seconds — the fifteen-minute window became five after the
        second failure, and paced guessing could resume early.

        Clock-pinned: the deadline stored with the first failure must
        survive later ones.
        """
        baseline = timezone.now()
        start = time.time()
        throttle.note_failure(_a_request(), "sam", now=start)

        # Nine more failures, five minutes in — past the old default.
        for _ in range(9):
            throttle.note_failure(_a_request(), "sam", now=start + 301)

        count, deadline = cache.get("login-fail-user:sam")
        self.assertEqual(count, 10)
        self.assertAlmostEqual(deadline - start, throttle.WINDOW_SECONDS, delta=1)

        # The row's own expiry, not just the deadline stored in the
        # value. An earlier version of this test checked only the value
        # and passed against the bug: the stored deadline was preserved
        # while the cache entry itself was being rewritten with the
        # 300-second default, so the counter vanished at five minutes
        # and the limit lifted early.
        # Five simulated minutes in, so about ten should be left — and
        # crucially not the 300 seconds the bug produced.
        # Measured from a baseline taken before the writes rather
        # than a fresh now(), so the assertion does not depend on how
        # long the test itself took.
        left = _row_expiry("login-fail-user:sam") - baseline
        self.assertGreater(
            left, timedelta(minutes=9), "the cache entry expires before the window does"
        )
        self.assertLess(left, timedelta(minutes=11), "the window was extended")

    def test_an_already_signed_in_person_cannot_guess_freely_at_admin(self):
        """`request.user` is theirs, not the account being guessed at,
        so reading it counted every failed guess as a success and
        cleared the counters instead of filling them.
        """
        cleaner = User.objects.create_user("crew", password=PASSWORD)
        self.client.force_login(cleaner)
        for _ in range(throttle.MAX_FAILURES):
            self.client.post(
                ADMIN_LOGIN, {"username": "sam", "password": "wrong", "next": "/admin/"}
            )
        refused = self.client.post(
            ADMIN_LOGIN, {"username": "sam", "password": "wrong", "next": "/admin/"}
        )
        self.assertEqual(refused.status_code, 429)

    def test_a_valid_sign_in_does_not_reset_the_address_count(self):
        """Clearing the shared per-address counter on success let
        somebody with one real account interleave sign-ins between
        guesses at other names, resetting the count each time and
        working through a list.
        """
        for _ in range(5):
            self.client.post(LOGIN, {"username": "nobody", "password": "wrong"})
        self.client.post(LOGIN, {"username": "sam", "password": PASSWORD})
        self.assertEqual(throttle._count("login-fail-ip:127.0.0.1"), 5)
        # Their own username counter did clear, which is the point of
        # not punishing a few mistypes.
        self.assertEqual(throttle._count("login-fail-user:sam"), 0)

    def test_an_enormous_username_is_still_counted(self):
        """The POST is not validated before counting, so an unbounded
        username went straight into a cache key — past the table's
        255-character column, turning a wrong password into a 500.

        Asserting a 200 was not enough, and that is the interesting
        part: `DatabaseCache` swallows the `DatabaseError` from an
        over-long key and returns False, so the page answers 200 while
        **nothing is counted**. This has to show the counting still
        happens — ten attempts from ten addresses, so only the username
        counter can be what trips the eleventh.
        """
        enormous = "x" * 5000
        for attempt in range(throttle.MAX_FAILURES):
            response = self.client.post(
                LOGIN,
                {"username": enormous, "password": "wrong-password"},
                HTTP_X_FORWARDED_FOR=f"10.1.0.{attempt + 1}",
            )
            self.assertEqual(response.status_code, 200, f"attempt {attempt + 1}")

        refused = self.client.post(
            LOGIN,
            {"username": enormous, "password": "wrong-password"},
            HTTP_X_FORWARDED_FOR="10.1.0.99",
        )
        self.assertEqual(refused.status_code, 429)

    def test_spelling_the_username_differently_shares_one_bucket(self):
        """Django normalizes the posted username with NFKC before it
        authenticates, so the fullwidth "ｓａｍ" signs in as "sam".
        Keying on the raw text gave every spelling its own ten-failure
        budget — a four-letter name with fullwidth forms has sixteen
        variants, so the per-account limit was really about 160 (#200).
        """
        spellings = ["sam", "ｓａｍ", "SAM", "Ｓａｍ", "sＡm"]
        for attempt in range(throttle.MAX_FAILURES):
            self.client.post(
                LOGIN,
                {
                    "username": spellings[attempt % len(spellings)],
                    "password": "wrong-password",
                },
                HTTP_X_FORWARDED_FOR=f"10.2.0.{attempt + 1}",
            )

        # Eleventh attempt: a fresh address, and the plain spelling.
        refused = self.client.post(
            LOGIN,
            {"username": "sam", "password": "wrong-password"},
            HTTP_X_FORWARDED_FOR="10.2.0.99",
        )
        self.assertEqual(refused.status_code, 429)
        self.assertEqual(throttle._count("login-fail-user:sam"), throttle.MAX_FAILURES)

    def test_setting_a_password_clears_that_persons_lockout(self):
        """The owner setting a password is the recovery path (ADR
        0021), and the 429 is returned before any password is checked —
        so docs/ADMIN_GUIDE.md's promise that it works straight away
        has to be made true, not assumed.
        """
        from apps.crm.tests._helpers import grant_role
        from apps.jobs.tests import _factories as f
        from apps.users.roles import Role

        for _ in range(throttle.MAX_FAILURES):
            self.guess(HTTP_X_FORWARDED_FOR="10.0.0.1")
        self.assertEqual(throttle._count("login-fail-user:sam"), throttle.MAX_FAILURES)

        owner = grant_role(f.user("boss"), Role.OWNER)
        self.client.force_login(owner)
        self.client.post(
            reverse("people:member", args=["sam"]),
            {"new_password1": "a-brand-new-password", "new_password2": "a-brand-new-password"},
        )
        self.assertEqual(throttle._count("login-fail-user:sam"), 0)


class WhatWasActuallyWrongTests(TestCase):
    """The two faults the audit found, which no amount of counting
    fixes on its own."""

    def test_the_cache_is_shared_across_processes(self):
        """F-SEC-1. Django's fallback is per-process LocMemCache and
        gunicorn runs three workers, so a limiter on it keeps three
        separate counts and lets three times the guesses through —
        while passing a test suite, because the runner is one process.
        Asserting the backend is the only way a single-process test can
        tell the difference.
        """
        self.assertEqual(
            settings.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.db.DatabaseCache",
        )

    def test_the_counter_really_lands_in_the_database(self):
        """And the table exists, so the backend above is not merely
        configured but working — a missing table would raise, not fall
        back."""
        cache.clear()
        user = User.objects.create_user("sam", password=PASSWORD)
        self.client.post(LOGIN, {"username": user.get_username(), "password": "wrong"})
        # Each entry is (count, deadline) so later failures can keep the
        # first one's expiry — see test_the_window_is_fifteen_minutes.
        count, deadline = cache.get("login-fail-user:sam")
        self.assertEqual(count, 1)
        self.assertGreater(deadline, time.time())

    def test_the_client_ip_is_the_client_not_the_proxy(self):
        """Caddy proxies every request, so REMOTE_ADDR is the proxy and
        counting it would make one global bucket.
        """
        request = self.client.request().wsgi_request
        request.META["REMOTE_ADDR"] = "172.18.0.2"
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.7"
        self.assertEqual(throttle.client_ip(request), "203.0.113.7")

    def test_a_forged_forwarded_header_cannot_choose_the_bucket(self):
        """Caddy **appends** the peer it spoke to, so the last entry is
        the real client. Reading the first would let anybody pick their
        own bucket by sending a header — worse than not counting,
        because it looks like it works.
        """
        request = self.client.request().wsgi_request
        request.META["HTTP_X_FORWARDED_FOR"] = "198.51.100.1, 203.0.113.7"
        self.assertEqual(throttle.client_ip(request), "203.0.113.7")

    def test_no_proxy_falls_back_to_the_peer(self):
        """Development has no proxy: the header is absent and
        REMOTE_ADDR is the client."""
        request = self.client.request().wsgi_request
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META.pop("HTTP_X_FORWARDED_FOR", None)
        self.assertEqual(throttle.client_ip(request), "127.0.0.1")
