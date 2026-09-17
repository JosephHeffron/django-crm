from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse


class HealthCheckViewTests(TestCase):
    def test_anonymous_user_gets_a_healthy_response(self):
        # Deliberately no login() call — monitoring/orchestration
        # tooling can't authenticate, so this must work unauthenticated.
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_reports_unhealthy_when_the_database_is_unreachable(self):
        with patch("apps.core.views.connection") as mock_connection:
            mock_connection.cursor.side_effect = Exception("simulated database outage")
            response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "error", "database": "error"})

    def test_post_is_not_allowed(self):
        response = self.client.post(reverse("core:health"))
        self.assertEqual(response.status_code, 405)
