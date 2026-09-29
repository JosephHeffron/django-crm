from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.crm.models import Note
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import ServiceType
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"


class PageTestCase(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("rep"), Role.SALES_REP)
        self.crew = grant_role(f.user("crew"), Role.CLEANER)
        self.customer = f.contact(self.owner, "Pat", "Gutters", phone="(585) 555-0101")
        self.job = f.job(self.customer, self.owner, lines=[(Decimal("2"), Decimal("87.50"))])

    def login(self, username):
        self.client.login(username=username, password=PASSWORD)


class JobDetailTests(PageTestCase):
    def test_sales_roles_see_prices_and_the_owner_sees_invoices(self):
        f.invoice(self.job, lines=[(Decimal("1"), Decimal("175"))])
        self.login("rep")
        response = self.client.get(self.job.get_absolute_url())
        self.assertContains(response, "$175.00")
        self.assertNotContains(response, "INV-")

        self.login("boss")
        self.assertContains(self.client.get(self.job.get_absolute_url()), "INV-")

    def test_assigned_cleaner_sees_the_visit_but_no_prices(self):
        f.assign(self.job, self.crew)
        Note.objects.create(author=self.owner, body="Bring the long ladder", job=self.job)
        self.login("crew")
        response = self.client.get(self.job.get_absolute_url())
        self.assertContains(response, "Pat Gutters")
        self.assertContains(response, 'href="tel:(585) 555-0101"')
        self.assertContains(response, "Bring the long ladder")
        self.assertNotContains(response, "$")
        self.assertNotContains(response, self.customer.get_absolute_url())

    def test_unassigned_cleaner_gets_404_not_403(self):
        self.login("crew")
        self.assertEqual(self.client.get(self.job.get_absolute_url()).status_code, 404)

    def test_anonymous_is_sent_to_login(self):
        self.assertEqual(self.client.get(self.job.get_absolute_url()).status_code, 302)


class QuoteDetailTests(PageTestCase):
    def test_sales_roles_see_the_quote(self):
        quote = f.quote(self.customer, self.rep, lines=[(Decimal("3"), Decimal("40"))])
        self.login("rep")
        response = self.client.get(quote.get_absolute_url())
        self.assertContains(response, quote.number)
        self.assertContains(response, "$120.00")

    def test_cleaners_are_refused(self):
        quote = f.quote(self.customer, self.rep)
        self.login("crew")
        self.assertEqual(self.client.get(quote.get_absolute_url()).status_code, 403)


class ServiceSettingsTests(PageTestCase):
    def test_only_the_owner_may_open_or_edit_the_catalog(self):
        service = f.service()
        urls = [reverse("jobs:service_list"), reverse("jobs:service_update", args=[service.pk])]
        for username, expected in (("boss", 200), ("rep", 403), ("crew", 403)):
            self.login(username)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, expected, (username, url))

    def test_owner_edits_price_interval_and_color(self):
        service = f.service()
        self.login("boss")
        response = self.client.post(
            reverse("jobs:service_update", args=[service.pk]),
            {
                "name": service.name,
                "description": "",
                "default_price": "199.00",
                "pricing_unit": ServiceType.PricingUnit.FLAT,
                "followup_interval_months": "4",
                "tone": "7",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("jobs:service_list"))
        service.refresh_from_db()
        self.assertEqual(
            (service.default_price, service.followup_interval_months, service.tone),
            (Decimal("199.00"), 4, 7),
        )

    def test_rep_cannot_post_an_edit(self):
        service = f.service()
        self.login("rep")
        response = self.client.post(
            reverse("jobs:service_update", args=[service.pk]), {"default_price": "1"}
        )
        self.assertEqual(response.status_code, 403)
