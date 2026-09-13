from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.crm.models import Activity, AuditLogEntry, Company, Contact, Deal, Lead
from apps.crm.tests._helpers import grant_staff

User = get_user_model()


class AuditLogEntryModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)

    def test_record_resolves_via_generic_foreign_key(self):
        entry = AuditLogEntry.objects.create(
            content_type=None,
            object_id=None,
            user=self.user,
            action=AuditLogEntry.Action.CREATED,
        )
        from django.contrib.contenttypes.models import ContentType

        entry.content_type = ContentType.objects.get_for_model(Company)
        entry.object_id = self.company.pk
        entry.save()
        self.assertEqual(entry.record, self.company)

    def test_str_includes_action_and_object_id(self):
        from django.contrib.contenttypes.models import ContentType

        entry = AuditLogEntry.objects.create(
            content_type=ContentType.objects.get_for_model(Company),
            object_id=self.company.pk,
            user=self.user,
            action=AuditLogEntry.Action.CREATED,
        )
        self.assertIn("Created", str(entry))
        self.assertIn(str(self.company.pk), str(entry))


class CompanyAuditLogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")

    def test_create_logs_a_created_entry_with_no_changes(self):
        self.client.post(
            reverse("crm:company_create"),
            {
                "name": "Acme Corp",
                "website": "",
                "phone": "",
                "industry": "",
                "notes": "",
                "is_active": "on",
            },
        )
        company = Company.objects.get(name="Acme Corp")
        entries = list(AuditLogEntry.objects.filter(object_id=company.pk))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].action, AuditLogEntry.Action.CREATED)
        self.assertEqual(entries[0].changes, {})
        self.assertEqual(entries[0].user, self.user)

    def test_update_logs_only_changed_fields(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        self.client.post(
            reverse("crm:company_update", args=[company.pk]),
            {
                "name": "Acme Corp",
                "website": "",
                "phone": "",
                "industry": "Software",
                "notes": "",
                "is_active": "on",
            },
        )
        entries = list(
            AuditLogEntry.objects.filter(object_id=company.pk, action=AuditLogEntry.Action.UPDATED)
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].changes, {"industry": ["", "Software"]})

    def test_no_op_update_does_not_log_an_entry(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        AuditLogEntry.objects.all().delete()
        self.client.post(
            reverse("crm:company_update", args=[company.pk]),
            {
                "name": "Acme Corp",
                "website": "",
                "phone": "",
                "industry": "",
                "notes": "",
                "is_active": "on",
            },
        )
        self.assertFalse(AuditLogEntry.objects.filter(object_id=company.pk).exists())

    def test_deactivate_logs_is_active_change(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        AuditLogEntry.objects.all().delete()
        self.client.post(reverse("crm:company_deactivate", args=[company.pk]))
        entries = list(AuditLogEntry.objects.filter(object_id=company.pk))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].changes, {"is_active": ["True", "False"]})

    def test_detail_page_shows_history(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        self.client.post(
            reverse("crm:company_update", args=[company.pk]),
            {
                "name": "Acme Corp",
                "website": "",
                "phone": "",
                "industry": "Software",
                "notes": "",
                "is_active": "on",
            },
        )
        response = self.client.get(company.get_absolute_url())
        self.assertContains(response, "History")
        self.assertContains(response, "Software")

    def test_empty_history_shows_placeholder(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        response = self.client.get(company.get_absolute_url())
        self.assertContains(response, "No history yet")


class ContactAuditLogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")

    def test_create_logs_a_created_entry(self):
        self.client.post(
            reverse("crm:contact_create"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "",
                "phone": "",
                "title": "",
                "notes": "",
                "is_active": "on",
            },
        )
        contact = Contact.objects.get(first_name="Ada")
        entries = list(AuditLogEntry.objects.filter(object_id=contact.pk))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].action, AuditLogEntry.Action.CREATED)

    def test_company_reassignment_is_logged_readably(self):
        contact = Contact.objects.create(first_name="X", last_name="Y", created_by=self.user)
        new_company = Company.objects.create(name="New Employer Inc", created_by=self.user)
        AuditLogEntry.objects.all().delete()

        self.client.post(
            reverse("crm:contact_update", args=[contact.pk]),
            {
                "first_name": "X",
                "last_name": "Y",
                "email": "",
                "phone": "",
                "title": "",
                "company": new_company.pk,
                "notes": "",
                "is_active": "on",
            },
        )
        entries = list(AuditLogEntry.objects.filter(object_id=contact.pk))
        self.assertEqual(entries[0].changes, {"company": [None, "New Employer Inc"]})

    def test_deactivate_logs_is_active_change(self):
        contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.user
        )
        AuditLogEntry.objects.all().delete()
        self.client.post(reverse("crm:contact_deactivate", args=[contact.pk]))
        entries = list(AuditLogEntry.objects.filter(object_id=contact.pk))
        self.assertEqual(entries[0].changes, {"is_active": ["True", "False"]})


class LeadAndConversionAuditLogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")

    def test_lead_create_logs_a_created_entry(self):
        self.client.post(
            reverse("crm:lead_create"),
            {
                "name": "Jane Prospect",
                "company_name": "",
                "email": "",
                "phone": "",
                "source": "other",
                "status": "new",
                "notes": "",
            },
        )
        lead = Lead.objects.get(name="Jane Prospect")
        self.assertTrue(AuditLogEntry.objects.filter(object_id=lead.pk, action="created").exists())

    def test_conversion_logs_entries_for_new_company_contact_deal_and_lead(self):
        lead = Lead.objects.create(name="Jane Prospect", created_by=self.user)
        AuditLogEntry.objects.all().delete()

        self.client.post(
            reverse("crm:lead_convert", args=[lead.pk]),
            {
                "new_company_name": "Jane Co",
                "contact_first_name": "Jane",
                "contact_last_name": "Prospect",
                "contact_email": "",
                "contact_phone": "",
                "create_deal": "on",
                "deal_title": "Jane deal",
                "deal_value": "",
            },
        )
        lead.refresh_from_db()

        self.assertTrue(
            AuditLogEntry.objects.filter(
                object_id=lead.converted_company.pk, action="created"
            ).exists()
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(
                object_id=lead.converted_contact.pk, action="created"
            ).exists()
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(
                object_id=lead.converted_deal.pk, action="created"
            ).exists()
        )
        lead_entry = AuditLogEntry.objects.get(object_id=lead.pk, action="updated")
        self.assertEqual(lead_entry.changes, {"status": ["new", "converted"]})

    def test_conversion_with_existing_company_does_not_log_a_spurious_creation(self):
        existing_company = Company.objects.create(name="Existing Co", created_by=self.user)
        lead = Lead.objects.create(name="Bob Prospect", created_by=self.user)
        AuditLogEntry.objects.all().delete()

        self.client.post(
            reverse("crm:lead_convert", args=[lead.pk]),
            {
                "existing_company": existing_company.pk,
                "contact_first_name": "Bob",
                "contact_last_name": "Prospect",
                "contact_email": "",
                "contact_phone": "",
                "create_deal": "",
                "deal_title": "",
                "deal_value": "",
            },
        )
        self.assertFalse(
            AuditLogEntry.objects.filter(object_id=existing_company.pk, action="created").exists()
        )


class DealAuditLogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)

    def test_create_logs_a_created_entry(self):
        self.client.post(
            reverse("crm:deal_create"),
            {
                "title": "Acme deal",
                "company": self.company.pk,
                "contact": "",
                "value": "",
                "stage": "prospecting",
                "probability": "",
                "expected_close_date": "",
                "notes": "",
            },
        )
        deal = Deal.objects.get(title="Acme deal")
        self.assertTrue(AuditLogEntry.objects.filter(object_id=deal.pk, action="created").exists())

    def test_stage_change_is_logged(self):
        deal = Deal.objects.create(title="Acme deal", company=self.company, created_by=self.user)
        AuditLogEntry.objects.all().delete()

        self.client.post(
            reverse("crm:deal_update", args=[deal.pk]),
            {
                "title": "Acme deal",
                "company": self.company.pk,
                "contact": "",
                "value": "",
                "stage": "closed_won",
                "probability": "",
                "expected_close_date": "",
                "notes": "",
            },
        )
        entries = list(
            AuditLogEntry.objects.filter(object_id=deal.pk, action=AuditLogEntry.Action.UPDATED)
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].changes, {"stage": ["prospecting", "closed_won"]})


class TaskAndActivityAreNotAuditedTests(TestCase):
    """Task and Activity are explicitly out of scope for this unit — see
    docs/DATABASE_DESIGN.md's Audit history section."""

    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)

    def test_creating_a_task_logs_nothing(self):
        self.client.post(
            reverse("crm:task_create"),
            {
                "title": "Follow up",
                "assigned_to": self.user.pk,
                "priority": "medium",
                "status": "pending",
            },
        )
        self.assertEqual(AuditLogEntry.objects.count(), 0)

    def test_creating_an_activity_logs_nothing(self):
        self.client.post(
            reverse("crm:activity_create"),
            {"activity_type": "note", "subject": "A note", "company": self.company.pk},
        )
        self.assertTrue(Activity.objects.filter(subject="A note").exists())
        self.assertEqual(AuditLogEntry.objects.count(), 0)
