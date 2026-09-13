"""Regression tests from the Phase 5 usability review
(logs/claude/phase-05-usability-review.md).

The most significant finding: Django's `{# ... #}` comment tag does
not support multi-line content — a multi-line comment renders as
literal text instead of being stripped, which is exactly what
`_activity_timeline.html` and `_audit_history.html` did (both fixed to
use `{% comment %}...{% endcomment %}` instead, which does support
multiple lines). This was live on every Company/Contact/Lead/Deal
detail page and no existing test caught it, since nothing asserted on
the *absence* of that text.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.crm.models import Company, Contact, Deal, Lead
from apps.crm.tests._helpers import grant_staff

User = get_user_model()


class TemplateCommentsAreNotLeakedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")

    def test_company_detail_does_not_leak_partial_comments(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        response = self.client.get(company.get_absolute_url())
        self.assertNotContains(response, "Reusable activity timeline")
        self.assertNotContains(response, "Reusable audit history")

    def test_contact_detail_does_not_leak_partial_comments(self):
        contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.user
        )
        response = self.client.get(contact.get_absolute_url())
        self.assertNotContains(response, "Reusable activity timeline")
        self.assertNotContains(response, "Reusable audit history")

    def test_lead_detail_does_not_leak_partial_comments(self):
        lead = Lead.objects.create(name="Jane Prospect", created_by=self.user)
        response = self.client.get(lead.get_absolute_url())
        self.assertNotContains(response, "Reusable activity timeline")

    def test_deal_detail_does_not_leak_partial_comments(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        deal = Deal.objects.create(title="Acme deal", company=company, created_by=self.user)
        response = self.client.get(deal.get_absolute_url())
        self.assertNotContains(response, "Reusable activity timeline")
        self.assertNotContains(response, "Reusable audit history")


class CreateEditFormsHaveCancelLinksTests(TestCase):
    """A create/edit form with no way back except the browser's own
    back button was a usability gap this review found across every
    CRUD form — Cancel should return to the record being edited, or
    the relevant list when creating."""

    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")

    def test_company_add_cancels_to_list(self):
        response = self.client.get("/companies/add/")
        self.assertContains(response, 'href="/companies/">Cancel')

    def test_company_edit_cancels_to_detail(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        response = self.client.get(f"/companies/{company.pk}/edit/")
        self.assertContains(response, f'href="{company.get_absolute_url()}">Cancel')

    def test_contact_add_cancels_to_list(self):
        response = self.client.get("/contacts/add/")
        self.assertContains(response, 'href="/contacts/">Cancel')

    def test_lead_add_cancels_to_list(self):
        response = self.client.get("/leads/add/")
        self.assertContains(response, 'href="/leads/">Cancel')

    def test_deal_add_cancels_to_list(self):
        response = self.client.get("/deals/add/")
        self.assertContains(response, 'href="/deals/">Cancel')

    def test_task_add_cancels_to_list(self):
        response = self.client.get("/tasks/add/")
        self.assertContains(response, 'href="/tasks/">Cancel')
