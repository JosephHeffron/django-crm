from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class IndexViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response.url)

    def test_authenticated_user_sees_the_dashboard(self):
        self.client.login(username="alice", password="correct-horse-battery")
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alice")

    def test_dashboard_shows_logout_control(self):
        self.client.login(username="alice", password="correct-horse-battery")
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, reverse("users:logout"))
