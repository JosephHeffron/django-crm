from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import get_resolver, reverse

User = get_user_model()


def route_names(resolver=None, prefix=""):
    """Every named route in the project, namespace included.

    Walks the real resolver rather than one app's urlpatterns, so a
    route mounted in any URLconf under any namespace is seen.
    """
    resolver = resolver or get_resolver()
    found = set()
    for pattern in resolver.url_patterns:
        if hasattr(pattern, "url_patterns"):
            namespace = getattr(pattern, "namespace", None)
            found |= route_names(pattern, f"{prefix}{namespace}:" if namespace else prefix)
        elif pattern.name:
            found.add(f"{prefix}{pattern.name}")
    return found


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

    def test_no_password_reset_route_exists_anywhere(self):
        """Every URLconf in the project, not just this app's.

        Two earlier versions of this test were weaker than they looked.
        One reversed `users:password_reset_confirm` with no arguments —
        which raises NoReverseMatch whether or not the route exists,
        because that route took uidb64 and token, so it could not fail
        for the reason its name gave. The other only looked in the
        `users` namespace, so a reset flow mounted in another URLconf
        would have been reachable with the test still green. Walking
        the resolver has neither weakness.
        """
        offenders = sorted(
            name for name in route_names() if "password_reset" in name.split(":")[-1]
        )
        self.assertEqual(offenders, [], "a password-reset route is registered again")

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
        self.assertEqual(
            sorted(name for name in route_names() if name.startswith("users:")),
            [
                "users:login",
                "users:logout",
                "users:password_change",
                "users:password_change_done",
            ],
        )
