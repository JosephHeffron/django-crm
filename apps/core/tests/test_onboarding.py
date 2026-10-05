from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.models import BusinessSettings, Goal
from apps.core.onboarding import checklist
from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.users.models import get_profile
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"
INDEX = reverse("core:index")
DISMISS = reverse("core:onboarding_dismiss")


class ChecklistTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.profile = get_profile(self.owner)

    def test_a_fresh_install_has_every_step_open(self):
        data = checklist(BusinessSettings(), self.profile)
        self.assertEqual((data["done"], data["total"], data["percent"]), (0, 5, 0))
        self.assertEqual(data["next"].label, "Name your business")

    def test_steps_tick_themselves_off_from_real_data(self):
        f.contact(self.owner)
        Goal.objects.create(metric=Goal.Metric.JOBS, target=Decimal("5"))
        business = BusinessSettings(name="Sample Exterior Co.", contact_phone="+1 555 010 0100")
        data = checklist(business, self.profile)
        self.assertEqual((data["done"], data["percent"]), (4, 80))
        self.assertEqual(data["next"].label, "Add your logo")

    def test_a_step_un_ticks_itself_when_the_data_goes_away(self):
        # Nothing is stored as a flag, so deleting the last customer
        # re-opens that step.
        contact = f.contact(self.owner)
        business = BusinessSettings(name="Sample Exterior Co.")
        self.assertIn("Add your first customer", self._done(business))
        contact.delete()
        self.assertNotIn("Add your first customer", self._done(business))

    def _done(self, business):
        return [step.label for step in checklist(business, self.profile)["steps"] if step.done]

    def test_the_list_disappears_once_everything_is_done(self):
        f.contact(self.owner)
        Goal.objects.create(metric=Goal.Metric.JOBS, target=Decimal("5"))
        business = BusinessSettings(
            name="Sample Exterior Co.",
            logo="branding/logo.png",
            contact_email="office@example.com",
        )
        self.assertIsNone(checklist(business, self.profile))

    def test_a_dismissed_list_stays_hidden(self):
        self.profile.onboarding_dismissed = True
        self.assertIsNone(checklist(BusinessSettings(), self.profile))


class ChecklistPageTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.client.login(username="boss", password=PASSWORD)

    def test_the_owner_sees_it_on_the_dashboard(self):
        response = self.client.get(INDEX)
        self.assertContains(response, "Finish setting up")
        self.assertContains(response, "Name your business")

    def test_hiding_it_keeps_it_hidden(self):
        response = self.client.post(DISMISS, {"next": INDEX})
        self.assertRedirects(response, INDEX)
        self.assertTrue(get_profile(self.owner).onboarding_dismissed)
        self.assertNotContains(self.client.get(INDEX), "Finish setting up")

    def test_dismissing_only_returns_to_this_site(self):
        response = self.client.post(DISMISS, {"next": "https://evil.example.com/"})
        self.assertRedirects(response, INDEX)

    def test_other_roles_never_see_it(self):
        for username, role in (("rep", Role.SALES_REP), ("crew", Role.CLEANER)):
            grant_role(f.user(username), role)
            self.client.login(username=username, password=PASSWORD)
            self.assertNotContains(self.client.get(INDEX), "Finish setting up")
            self.assertEqual(self.client.post(DISMISS).status_code, 403)
