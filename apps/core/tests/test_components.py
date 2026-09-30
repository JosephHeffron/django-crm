from django.test import TestCase
from django.urls import reverse

from apps.crm.models import Contact
from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"


class StyleguideTests(TestCase):
    def test_owner_only(self):
        for username, role, expected in (
            ("boss", Role.OWNER, 200),
            ("rep", Role.SALES_REP, 403),
            ("crew", Role.CLEANER, 403),
        ):
            grant_role(f.user(username), role)
            self.client.login(username=username, password=PASSWORD)
            self.assertEqual(self.client.get(reverse("core:styleguide")).status_code, expected)

    def test_renders_components_with_sample_data_only(self):
        grant_role(f.user("boss"), Role.OWNER)
        self.client.login(username="boss", password=PASSWORD)
        response = self.client.get(reverse("core:styleguide"))
        for marker in (
            "stat-card is-arc",
            "segmented",
            "section-card",
            "password-rules",
            "nav-dashboard",
        ):
            self.assertContains(response, marker)
        self.assertContains(response, "Showing 21–30 of 137 entries")


class PaginationTests(TestCase):
    def setUp(self):
        self.rep = grant_role(f.user("rep"), Role.SALES_REP)
        self.client.login(username="rep", password=PASSWORD)
        for i in range(30):
            Contact.objects.create(
                first_name=f"Lee{i:02d}", last_name="X", status="lead", created_by=self.rep
            )

    def test_page_size_choice_and_bad_values(self):
        url = reverse("crm:contact_list")
        self.assertEqual(len(self.client.get(url).context["contacts"]), 25)
        self.assertEqual(len(self.client.get(url, {"per_page": "10"}).context["contacts"]), 10)
        for bad in ("7", "1000", "x"):
            self.assertEqual(len(self.client.get(url, {"per_page": bad}).context["contacts"]), 25)

    def test_shows_range_numbers_and_keeps_filters(self):
        response = self.client.get(reverse("crm:contact_list"), {"stage": "lead", "per_page": "10"})
        self.assertContains(response, "Showing 1–10 of 30 entries")
        self.assertContains(response, "?stage=lead&amp;per_page=10&amp;page=2")
        self.assertContains(response, 'aria-current="page">1<')
        # The page-size form carries the other filters as hidden fields.
        self.assertContains(response, '<input type="hidden" name="stage" value="lead">')
