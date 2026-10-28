"""Getting back in after forgetting a password (Phase 22.5 unit 1).

Until now the only way back in was the owner opening the Django admin
(`docs/VPS_AUDIT.md` F-CRM-2), which is not an answer for a business
with staff.

Two of these tests exist for things Django gives us and we must not
accidentally take away — that an unknown address reveals nothing, and
that a link works once — and one exists for a trap of this project's
own: the link has to point at the CRM even when the request arrived at
the website's hostname.
"""

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

User = get_user_model()

PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "a-different-long-password"
RESET = reverse("users:password_reset")


def link_in(message):
    """The reset URL out of the email body."""
    found = re.search(r"https?://\S+/accounts/password-reset/\S+", message.body)
    assert found, message.body
    return found.group(0)


class AskingForALinkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sam", email="sam@example.test", password=PASSWORD)

    def test_the_sign_in_page_offers_it(self):
        """A reset flow nobody can find is not a reset flow."""
        response = self.client.get(reverse("users:login"))
        self.assertContains(response, RESET)

    def test_a_known_address_gets_an_email_with_a_working_link(self):
        self.client.post(RESET, {"email": "sam@example.test"})
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["sam@example.test"])
        self.assertIn("password", sent.subject.lower())
        self.assertEqual(self.client.get(link_in(sent)).status_code, 302)

    def test_an_unknown_address_says_exactly_the_same_thing(self):
        """Otherwise this page answers "does this person have an
        account here?" for anybody who asks."""
        known = self.client.post(RESET, {"email": "sam@example.test"}, follow=True)
        mail.outbox.clear()
        unknown = self.client.post(RESET, {"email": "nobody@example.test"}, follow=True)
        self.assertEqual(unknown.status_code, known.status_code)
        self.assertEqual(unknown.content, known.content)
        self.assertEqual(mail.outbox, [], "an email went to an address with no account")

    def test_a_deactivated_person_gets_nothing(self):
        """Deactivating an account has to actually keep somebody out,
        and Django's reset form is one of the places that could let
        them back in."""
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.client.post(RESET, {"email": "sam@example.test"})
        self.assertEqual(mail.outbox, [])


class UsingTheLinkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sam", email="sam@example.test", password=PASSWORD)
        self.client.post(RESET, {"email": "sam@example.test"})
        self.link = link_in(mail.outbox[0])

    def set_password(self, link=None):
        """Follow the link to the form Django redirects to, then post."""
        page = self.client.get(link or self.link, follow=True)
        return self.client.post(
            page.redirect_chain[-1][0] if page.redirect_chain else (link or self.link),
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )

    def test_the_new_password_works_and_the_old_one_stops(self):
        self.set_password()
        self.assertTrue(self.client.login(username="sam", password=NEW_PASSWORD))
        self.client.logout()
        self.assertFalse(self.client.login(username="sam", password=PASSWORD))

    def test_the_link_only_works_once(self):
        """A reset link in an inbox is a key. It has to stop being one
        the moment it is used."""
        self.set_password()
        self.client.logout()
        again = self.client.get(self.link, follow=True)
        self.assertContains(again, "expired")
        self.assertNotContains(again, "Save the new password")


@override_settings(
    CRM_SITE_HOST="crm.example.test",
    ALLOWED_HOSTS=["crm.example.test", "www.example.test", "testserver"],
)
class EmailLinkHostTests(TestCase):
    """The trap this project will walk into on its own.

    Django builds the link from the request's host. Once the public
    website's hostnames join ALLOWED_HOSTS for the booking form, a
    reset asked for through the website would email a link to the
    website — which Caddy serves from static files and never proxies
    to Django. A dead link, in the one email that has to work, found
    by somebody already locked out.
    """

    def setUp(self):
        User.objects.create_user("sam", email="sam@example.test", password=PASSWORD)

    def test_the_link_points_at_the_crm_whatever_host_was_asked(self):
        self.client.post(RESET, {"email": "sam@example.test"}, HTTP_HOST="www.example.test")
        self.assertEqual(len(mail.outbox), 1)
        link = link_in(mail.outbox[0])
        self.assertIn("crm.example.test", link)
        self.assertNotIn("www.example.test", link)

    @override_settings(CRM_SITE_HOST="")
    def test_unset_falls_back_to_the_host_that_asked(self):
        """Blank must stay a no-op, or development and today's
        single-host deployment would both break."""
        self.client.post(RESET, {"email": "sam@example.test"}, HTTP_HOST="crm.example.test")
        self.assertIn("crm.example.test", link_in(mail.outbox[0]))


class MailConfigurationTests(TestCase):
    def test_development_never_sends(self):
        """Printed, not sent (ADR 0019): nothing run on a workstation
        — a test, a seed, a shell — can reach a real person."""
        from config.settings import development

        self.assertEqual(
            development.EMAIL_BACKEND, "django.core.mail.backends.console.EmailBackend"
        )

    def test_production_refuses_to_start_without_mail_settings(self):
        """Required, not defaulted: a container that boots happily and
        cannot send is the failure nobody notices until somebody is
        locked out."""
        import importlib
        import os
        from unittest import mock

        base = {
            "DJANGO_SECRET_KEY": "x",
            "DJANGO_ALLOWED_HOSTS": "crm.example.test",
            "POSTGRES_DB": "x",
            "POSTGRES_USER": "x",
            "POSTGRES_PASSWORD": "x",
            "EMAIL_HOST": "smtp.example.test",
            "EMAIL_HOST_USER": "crm@example.test",
            "EMAIL_HOST_PASSWORD": "x",
        }
        for missing in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"):
            environment = {key: value for key, value in base.items() if key != missing}
            with mock.patch.dict(os.environ, environment, clear=True):
                with self.assertRaises(KeyError, msg=f"{missing} was not required"):
                    importlib.reload(importlib.import_module("config.settings.production"))

        # Reload once more with everything present, so a later test in
        # the same process does not see a half-imported module.
        with mock.patch.dict(os.environ, base, clear=True):
            importlib.reload(importlib.import_module("config.settings.production"))
