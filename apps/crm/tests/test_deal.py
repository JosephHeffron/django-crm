from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.crm.models import Company, Contact, Deal

User = get_user_model()


class DealModelTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user("creator", password="pw")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.creator)
        self.contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.creator
        )

    def test_deal_with_company_only(self):
        deal = Deal.objects.create(title="Acme deal", company=self.company, created_by=self.creator)
        self.assertEqual(deal.company, self.company)
        self.assertIsNone(deal.contact)

    def test_deal_with_contact_only(self):
        deal = Deal.objects.create(title="Ada deal", contact=self.contact, created_by=self.creator)
        self.assertIsNone(deal.company)
        self.assertEqual(deal.contact, self.contact)

    def test_deal_with_both_company_and_contact(self):
        deal = Deal.objects.create(
            title="Acme+Ada deal",
            company=self.company,
            contact=self.contact,
            created_by=self.creator,
        )
        self.assertEqual(deal.company, self.company)
        self.assertEqual(deal.contact, self.contact)

    def test_deal_requires_company_or_contact(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Deal.objects.create(title="Orphan deal", created_by=self.creator)

    def test_default_stage_is_open(self):
        deal = Deal.objects.create(title="Acme deal", company=self.company, created_by=self.creator)
        self.assertEqual(deal.stage, Deal.Stage.PROSPECTING)
        self.assertTrue(deal.is_open)

    def test_closed_won_is_not_open(self):
        deal = Deal.objects.create(
            title="Acme deal",
            company=self.company,
            created_by=self.creator,
            stage=Deal.Stage.CLOSED_WON,
        )
        self.assertFalse(deal.is_open)

    def test_closed_lost_is_not_open(self):
        deal = Deal.objects.create(
            title="Acme deal",
            company=self.company,
            created_by=self.creator,
            stage=Deal.Stage.CLOSED_LOST,
        )
        self.assertFalse(deal.is_open)

    def test_company_delete_is_protected_when_referenced_by_deal(self):
        Deal.objects.create(title="Acme deal", company=self.company, created_by=self.creator)
        with self.assertRaises(ProtectedError):
            self.company.delete()

    def test_contact_delete_is_protected_when_referenced_by_deal(self):
        Deal.objects.create(title="Ada deal", contact=self.contact, created_by=self.creator)
        with self.assertRaises(ProtectedError):
            self.contact.delete()
