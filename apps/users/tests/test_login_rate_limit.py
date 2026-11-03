"""Refusing endless password guesses (ADR 0020).

There is no MFA until Phase 23 and unit 3 puts this app on the public
internet, so a password is the only thing between a guesser and the
business's records. `docs/VPS_AUDIT.md` F-SEC-1 and F-PUB-2 recorded
that neither login page counted attempts.

Two of these tests exist for the things that were *actually* wrong,
neither of which is the counting: the cache has to be shared across
gunicorn's workers, and the client IP has to be the client's.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.users import throttle

User = get_user_model()

PASSWORD = "correct-horse-battery"
LOGIN = reverse("users:login")
ADMIN_LOGIN = "/admin/login/"


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
        self.assertEqual(cache.get("login-fail-user:sam"), None)
        self.assertEqual(cache.get("login-fail-ip:127.0.0.1"), None)

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
        self.assertEqual(cache.get("login-fail-user:sam"), 1)

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
