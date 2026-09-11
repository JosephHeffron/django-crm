from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.crm.models import Company

User = get_user_model()


class CompanyModelTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user("creator", password="pw")
        self.owner = User.objects.create_user("owner", password="pw")

    def test_create_company_with_defaults(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.creator)
        self.assertTrue(company.is_active)
        self.assertIsNone(company.owner)
        self.assertEqual(str(company), "Acme Corp")

    def test_owner_is_optional(self):
        company = Company.objects.create(
            name="Acme Corp", created_by=self.creator, owner=self.owner
        )
        self.assertEqual(company.owner, self.owner)

    def test_created_by_is_required(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Company.objects.create(name="No Creator")

    def test_owner_delete_is_protected(self):
        Company.objects.create(name="Acme Corp", created_by=self.creator, owner=self.owner)
        with self.assertRaises(ProtectedError):
            self.owner.delete()

    def test_created_by_delete_is_protected(self):
        Company.objects.create(name="Acme Corp", created_by=self.creator)
        with self.assertRaises(ProtectedError):
            self.creator.delete()
