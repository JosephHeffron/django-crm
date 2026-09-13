from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.crm.models import Company, Contact, Deal, Lead
from apps.crm.tests._helpers import grant_staff

User = get_user_model()


class LeadListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:lead_list"))
        self.assertEqual(response.status_code, 302)

    def test_empty_list_shows_no_leads_message(self):
        response = self.client.get(reverse("crm:lead_list"))
        self.assertContains(response, "No leads found")

    def test_list_shows_leads(self):
        Lead.objects.create(name="Jane Prospect", created_by=self.user)
        response = self.client.get(reverse("crm:lead_list"))
        self.assertContains(response, "Jane Prospect")

    def test_search_matches_name_company_or_email(self):
        Lead.objects.create(
            name="Jane Prospect",
            company_name="Prospect Inc",
            email="jane@prospect.example",
            created_by=self.user,
        )
        Lead.objects.create(name="Bob Other", created_by=self.user)

        response = self.client.get(reverse("crm:lead_list"), {"q": "Prospect Inc"})
        self.assertContains(response, "Jane Prospect")
        self.assertNotContains(response, "Bob Other")

    def test_status_filter(self):
        Lead.objects.create(name="New Lead", status=Lead.Status.NEW, created_by=self.user)
        Lead.objects.create(
            name="Qualified Lead", status=Lead.Status.QUALIFIED, created_by=self.user
        )

        response = self.client.get(reverse("crm:lead_list"), {"status": "qualified"})
        self.assertContains(response, "Qualified Lead")
        self.assertNotContains(response, "New Lead")

    def test_invalid_status_param_is_ignored(self):
        Lead.objects.create(name="Some Lead", created_by=self.user)
        response = self.client.get(reverse("crm:lead_list"), {"status": "not-a-real-status"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Some Lead")


class LeadDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.lead = Lead.objects.create(name="Jane Prospect", created_by=self.user)

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(self.lead.get_absolute_url())
        self.assertEqual(response.status_code, 302)

    def test_detail_shows_lead_fields(self):
        response = self.client.get(self.lead.get_absolute_url())
        self.assertContains(response, "Jane Prospect")

    def test_unconverted_lead_shows_convert_link(self):
        response = self.client.get(self.lead.get_absolute_url())
        self.assertContains(response, reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}))

    def test_converted_lead_hides_convert_link(self):
        self.lead.status = Lead.Status.CONVERTED
        self.lead.save()
        response = self.client.get(self.lead.get_absolute_url())
        self.assertNotContains(response, reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}))

    def test_nonexistent_lead_returns_404(self):
        response = self.client.get(reverse("crm:lead_detail", kwargs={"pk": 999999}))
        self.assertEqual(response.status_code, 404)


class LeadCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:lead_create"))
        self.assertEqual(response.status_code, 302)

    def test_successful_create_sets_created_by_and_defaults(self):
        # status is a required form field (no blank=True on the model),
        # so a real browser always submits whatever <select> option was
        # selected — the model's default=NEW only applies when status
        # is absent from a .save() call entirely, not from bound POST
        # data missing a value for a required field.
        response = self.client.post(
            reverse("crm:lead_create"),
            {"name": "Jane Prospect", "source": "website", "status": "new"},
        )
        lead = Lead.objects.get(name="Jane Prospect")
        self.assertRedirects(response, lead.get_absolute_url())
        self.assertEqual(lead.created_by, self.user)
        self.assertEqual(lead.status, Lead.Status.NEW)

    def test_converted_is_not_a_selectable_status_choice(self):
        response = self.client.get(reverse("crm:lead_create"))
        self.assertNotContains(response, '<option value="converted">')

    def test_missing_required_field_does_not_create(self):
        response = self.client.post(reverse("crm:lead_create"), {"name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Lead.objects.exists())


class LeadUpdateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.lead = Lead.objects.create(name="Jane Prospect", created_by=self.user)

    def test_successful_update(self):
        response = self.client.post(
            reverse("crm:lead_update", kwargs={"pk": self.lead.pk}),
            {"name": "Jane Prospect", "status": "contacted", "source": "website"},
        )
        self.lead.refresh_from_db()
        self.assertRedirects(response, self.lead.get_absolute_url())
        self.assertEqual(self.lead.status, Lead.Status.CONTACTED)

    def test_edit_form_disables_status_once_converted(self):
        self.lead.status = Lead.Status.CONVERTED
        self.lead.save()
        response = self.client.get(reverse("crm:lead_update", kwargs={"pk": self.lead.pk}))
        self.assertTrue(response.context["form"].fields["status"].disabled)


class LeadConvertViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.lead = Lead.objects.create(
            name="Jane Prospect",
            company_name="Prospect Inc",
            email="jane@prospect.example",
            phone="555-1234",
            created_by=self.user,
        )

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}))
        self.assertEqual(response.status_code, 302)

    def test_get_prefills_from_lead(self):
        response = self.client.get(reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}))
        self.assertContains(response, "Prospect Inc")
        self.assertContains(response, "Jane")
        self.assertContains(response, "Prospect")
        self.assertContains(response, "jane@prospect.example")

    def test_get_on_already_converted_lead_redirects_with_message(self):
        self.lead.status = Lead.Status.CONVERTED
        self.lead.save()
        response = self.client.get(
            reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}), follow=True
        )
        self.assertRedirects(response, self.lead.get_absolute_url())
        self.assertContains(response, "already been converted")

    def test_convert_creates_new_company_contact_and_deal(self):
        response = self.client.post(
            reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}),
            {
                "new_company_name": "Prospect Inc",
                "contact_first_name": "Jane",
                "contact_last_name": "Prospect",
                "contact_email": "jane@prospect.example",
                "contact_phone": "555-1234",
                "create_deal": "on",
                "deal_title": "Prospect Inc deal",
                "deal_value": "5000",
            },
        )
        self.lead.refresh_from_db()
        self.assertRedirects(response, self.lead.get_absolute_url())
        self.assertEqual(self.lead.status, Lead.Status.CONVERTED)
        self.assertIsNotNone(self.lead.converted_at)

        company = Company.objects.get(name="Prospect Inc")
        contact = Contact.objects.get(first_name="Jane", last_name="Prospect")
        deal = Deal.objects.get(title="Prospect Inc deal")

        self.assertEqual(self.lead.converted_company, company)
        self.assertEqual(self.lead.converted_contact, contact)
        self.assertEqual(self.lead.converted_deal, deal)
        self.assertEqual(contact.company, company)
        self.assertEqual(deal.company, company)
        self.assertEqual(deal.contact, contact)
        self.assertEqual(deal.value, 5000)
        self.assertEqual(contact.created_by, self.user)
        self.assertEqual(company.created_by, self.user)
        self.assertEqual(deal.created_by, self.user)

    def test_convert_links_existing_company_instead_of_creating_one(self):
        existing = Company.objects.create(name="Existing Co", created_by=self.user)
        self.client.post(
            reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}),
            {
                "existing_company": existing.pk,
                "contact_first_name": "Jane",
                "contact_last_name": "Prospect",
            },
        )
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.converted_company, existing)
        self.assertEqual(Company.objects.count(), 1)

    def test_convert_without_create_deal_creates_no_deal(self):
        self.client.post(
            reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}),
            {"contact_first_name": "Jane", "contact_last_name": "Prospect"},
        )
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.converted_deal)
        self.assertFalse(Deal.objects.exists())

    def test_convert_without_any_company_leaves_contact_unlinked(self):
        self.client.post(
            reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}),
            {"contact_first_name": "Jane", "contact_last_name": "Prospect"},
        )
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.converted_company)
        self.assertIsNone(self.lead.converted_contact.company)

    def test_choosing_both_existing_and_new_company_is_rejected(self):
        existing = Company.objects.create(name="Existing Co", created_by=self.user)
        response = self.client.post(
            reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}),
            {
                "existing_company": existing.pk,
                "new_company_name": "Another Co",
                "contact_first_name": "Jane",
                "contact_last_name": "Prospect",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.NEW)

    def test_create_deal_without_title_is_rejected(self):
        response = self.client.post(
            reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}),
            {
                "contact_first_name": "Jane",
                "contact_last_name": "Prospect",
                "create_deal": "on",
                "deal_title": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.NEW)

    def test_missing_contact_name_is_rejected(self):
        response = self.client.post(
            reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}),
            {"contact_first_name": "", "contact_last_name": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.NEW)

    def test_post_on_already_converted_lead_does_not_duplicate(self):
        self.lead.status = Lead.Status.CONVERTED
        self.lead.save()
        response = self.client.post(
            reverse("crm:lead_convert", kwargs={"pk": self.lead.pk}),
            {"contact_first_name": "Jane", "contact_last_name": "Prospect"},
        )
        self.assertRedirects(response, self.lead.get_absolute_url())
        self.assertFalse(Contact.objects.exists())
