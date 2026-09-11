from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.crm.models import Company, Contact

User = get_user_model()


class ContactModelTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user("creator", password="pw")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.creator)

    def test_create_contact_with_company(self):
        contact = Contact.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            created_by=self.creator,
        )
        self.assertEqual(contact.company, self.company)
        self.assertEqual(str(contact), "Ada Lovelace")

    def test_create_contact_without_company(self):
        contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.creator
        )
        self.assertIsNone(contact.company)

    def test_company_deletion_sets_null_not_cascade(self):
        contact = Contact.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            created_by=self.creator,
        )
        self.company.delete()
        contact.refresh_from_db()
        self.assertIsNone(contact.company)

    def test_related_name_from_company(self):
        contact = Contact.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            created_by=self.creator,
        )
        self.assertIn(contact, self.company.contacts.all())
