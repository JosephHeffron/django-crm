from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.crm.models import Company, Contact, Deal, Lead

User = get_user_model()


class LeadModelTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user("creator", password="pw")

    def test_create_lead_with_defaults(self):
        lead = Lead.objects.create(name="Jane Prospect", created_by=self.creator)
        self.assertEqual(lead.status, Lead.Status.NEW)
        self.assertEqual(lead.source, Lead.Source.OTHER)
        self.assertEqual(lead.company_name, "")
        self.assertEqual(str(lead), "Jane Prospect")

    def test_lead_has_no_company_foreign_key(self):
        # Deliberate design choice — a Lead only carries a free-text
        # company_name until conversion creates/links a real Company.
        self.assertNotIn("company", [f.name for f in Lead._meta.get_fields()])

    def test_conversion_records_targets(self):
        lead = Lead.objects.create(
            name="Jane Prospect", created_by=self.creator, status=Lead.Status.QUALIFIED
        )
        company = Company.objects.create(name="Prospect Inc", created_by=self.creator)
        contact = Contact.objects.create(
            first_name="Jane",
            last_name="Prospect",
            company=company,
            created_by=self.creator,
        )
        deal = Deal.objects.create(title="Prospect deal", company=company, created_by=self.creator)

        lead.status = Lead.Status.CONVERTED
        lead.converted_at = timezone.now()
        lead.converted_company = company
        lead.converted_contact = contact
        lead.converted_deal = deal
        lead.save()

        lead.refresh_from_db()
        self.assertEqual(lead.status, Lead.Status.CONVERTED)
        self.assertIsNotNone(lead.converted_at)
        self.assertEqual(lead.converted_company, company)
        self.assertEqual(lead.converted_contact, contact)
        self.assertEqual(lead.converted_deal, deal)

    def test_converted_company_deletion_sets_null(self):
        company = Company.objects.create(name="Prospect Inc", created_by=self.creator)
        lead = Lead.objects.create(
            name="Jane Prospect",
            created_by=self.creator,
            status=Lead.Status.CONVERTED,
            converted_company=company,
        )
        company.delete()
        lead.refresh_from_db()
        self.assertIsNone(lead.converted_company)
