from django.template.loader import render_to_string
from django.test import TestCase, override_settings


@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
class NotFoundPageTests(TestCase):
    # Django only uses the custom 404.html template when DEBUG=False —
    # with DEBUG=True it shows its own debug traceback page instead.

    def test_unknown_url_returns_custom_404(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)


class ServerErrorPageTests(TestCase):
    # Django's server_error view renders 500.html without a
    # RequestContext (no context processors, no `user`), so it can't be
    # exercised via a normal client request without an actual unhandled
    # exception. Render the template directly instead — this still
    # verifies the template itself is valid and self-contained.

    def test_500_template_renders_without_request_context(self):
        rendered = render_to_string("500.html")
        self.assertIn("Something went wrong", rendered)
