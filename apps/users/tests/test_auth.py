from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
