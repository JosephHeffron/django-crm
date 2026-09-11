from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.crm.models import Activity, Company, Contact, Deal, Lead

User = get_user_model()


class ActivityModelTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user("creator", password="pw")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.creator)

    def test_activity_with_company_only(self):
        activity = Activity.objects.create(
            activity_type=Activity.ActivityType.CALL,
            subject="Intro call",
            company=self.company,
            created_by=self.creator,
        )
        self.assertEqual(str(activity), "Intro call")
        self.assertIn(activity, self.company.activities.all())

    def test_activity_requires_at_least_one_relation(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Activity.objects.create(
                activity_type=Activity.ActivityType.NOTE,
                subject="Orphan note",
                created_by=self.creator,
            )

    def test_activity_with_contact_only(self):
        contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.creator
        )
        activity = Activity.objects.create(
            activity_type=Activity.ActivityType.EMAIL,
            subject="Follow-up email",
            contact=contact,
            created_by=self.creator,
        )
        self.assertEqual(activity.contact, contact)

    def test_activity_with_lead_only(self):
        lead = Lead.objects.create(name="Jane Prospect", created_by=self.creator)
        activity = Activity.objects.create(
            activity_type=Activity.ActivityType.NOTE,
            subject="Left voicemail",
            lead=lead,
            created_by=self.creator,
        )
        self.assertEqual(activity.lead, lead)

    def test_activity_with_deal_only(self):
        deal = Deal.objects.create(title="Acme deal", company=self.company, created_by=self.creator)
        activity = Activity.objects.create(
            activity_type=Activity.ActivityType.MEETING,
            subject="Proposal review",
            deal=deal,
            created_by=self.creator,
        )
        self.assertEqual(activity.deal, deal)

    def test_company_deletion_cascades_to_activity(self):
        activity = Activity.objects.create(
            activity_type=Activity.ActivityType.NOTE,
            subject="Note about Acme",
            company=self.company,
            created_by=self.creator,
        )
        self.company.delete()
        self.assertFalse(Activity.objects.filter(pk=activity.pk).exists())

    def test_activity_type_choices_are_enforced_in_forms_not_the_db(self):
        # CharField choices aren't a DB-level constraint by default in
        # Django/Postgres — only max_length is. A value that's the wrong
        # choice but within max_length is accepted by .create(); it's
        # ModelForm/admin validation (full_clean()) that rejects bad
        # choices, not the schema itself.
        activity = Activity.objects.create(
            activity_type="bogus",
            subject="Should be rejected by forms, not the DB",
            company=self.company,
            created_by=self.creator,
        )
        self.assertEqual(activity.activity_type, "bogus")
