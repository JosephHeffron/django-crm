from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

User = get_user_model()


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")

    def test_login_page_renders(self):
        response = self.client.get(reverse("users:login"))
        self.assertEqual(response.status_code, 200)

    def test_successful_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("users:login"),
            {"username": "alice", "password": "correct-horse-battery"},
        )
        self.assertRedirects(response, reverse("core:index"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_failed_login_does_not_authenticate(self):
        response = self.client.post(
            reverse("users:login"),
            {"username": "alice", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["user"].is_authenticated)

    def test_login_required_redirect_preserves_next(self):
        response = self.client.get(reverse("core:index"))
        self.assertRedirects(response, f"{reverse('users:login')}?next={reverse('core:index')}")


class LogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")

    def test_logout_ends_the_session(self):
        self.client.login(username="alice", password="correct-horse-battery")
        response = self.client.post(reverse("users:logout"))
        self.assertRedirects(response, reverse("users:login"))

        # session should no longer be authenticated
        response = self.client.get(reverse("core:index"))
        self.assertRedirects(response, f"{reverse('users:login')}?next={reverse('core:index')}")

    def test_logout_requires_post(self):
        # Django 4.1+ LogoutView only accepts POST — GET should not log out.
        self.client.login(username="alice", password="correct-horse-battery")
        response = self.client.get(reverse("users:logout"))
        self.assertEqual(response.status_code, 405)


class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")

    def test_successful_password_change_redirects_to_done_page(self):
        # Regression test: PasswordChangeView's default success_url resolves
        # an unnamespaced "password_change_done", which doesn't exist since
        # this URLconf only registers it as "users:password_change_done" —
        # caught by review, reproduces as NoReverseMatch without the
        # explicit success_url set in urls.py.
        response = self.client.post(
            reverse("users:password_change"),
            {
                "old_password": "correct-horse-battery",
                "new_password1": "new-correct-horse-battery",
                "new_password2": "new-correct-horse-battery",
            },
        )
        self.assertRedirects(response, reverse("users:password_change_done"))

        self.client.logout()
        self.assertTrue(self.client.login(username="alice", password="new-correct-horse-battery"))


class TheAuthSurfaceIsClosedTests(TestCase):
    """What `/accounts/` offers, pinned (ADR 0021).

    This app sends no email, so there is no password-reset flow — the
    owner sets passwords from the Team page instead. That is a decision,
    not an omission, and it was briefly reversed: #188 added a reset
    flow that could never deliver on the target host, because
    DigitalOcean blocks outbound SMTP by default. If somebody wires one
    up again without reading ADR 0021, this fails and points at it.
    """

    def test_there_is_no_password_reset_route(self):
        for name in (
            "password_reset",
            "password_reset_done",
            "password_reset_confirm",
            "password_reset_complete",
        ):
            with self.assertRaises(NoReverseMatch, msg=f"users:{name} exists again"):
                reverse(f"users:{name}")

    def test_the_sign_in_page_offers_no_reset_link(self):
        """The route being gone is not enough — a link to it would be a
        500 on the page every locked-out person reaches first."""
        page = self.client.get(reverse("users:login")).content.decode().lower()
        for phrase in ("forgot", "reset"):
            self.assertNotIn(phrase, page)

    def test_the_only_auth_views_are_the_four_expected(self):
        """docs/SECURITY_REVIEW.md claims the auth surface is login,
        logout and an authenticated password change. #188 made that
        claim false for four days without anybody noticing, so it is
        asserted here rather than only written down.
        """
        from apps.users import urls

        self.assertEqual(
            sorted(pattern.name for pattern in urls.urlpatterns),
            ["login", "logout", "password_change", "password_change_done"],
        )
