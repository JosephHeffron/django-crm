from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse

User = get_user_model()


@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
class NotFoundPageTests(TestCase):
    # Django only uses the custom 404.html template when DEBUG=False —
    # with DEBUG=True it shows its own debug traceback page instead.

    def test_unknown_url_returns_custom_404(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)


@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
class PermissionDeniedPageTests(TestCase):
    # Same DEBUG-gated mechanism as the 404 page (docs/PERMISSIONS.md) —
    # a permission-gated view is the natural way to trigger a real 403.

    def test_forbidden_view_returns_custom_403(self):
        User.objects.create_user("bob", password="correct-horse-battery")
        self.client.login(username="bob", password="correct-horse-battery")
        response = self.client.get(reverse("crm:company_create"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Permission denied", status_code=403)


class ServerErrorPageTests(TestCase):
    # Django's server_error view renders 500.html without a
    # RequestContext (no context processors, no `user`), so it can't be
    # exercised via a normal client request without an actual unhandled
    # exception. Render the template directly instead — this still
    # verifies the template itself is valid and self-contained.

    def test_500_template_renders_without_request_context(self):
        rendered = render_to_string("500.html")
        self.assertIn("Something went wrong", rendered)
