from django.contrib.auth import get_user_model
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

    def test_activity_with_no_relation_is_allowed_at_the_db_level(self):
        # The activity_has_related_object CheckConstraint was removed
        # when Activity's relation FKs changed from CASCADE to SET_NULL
        # (docs/DATABASE_REVIEW.md finding #2) — a constraint requiring
        # "at least one" is incompatible with a relation gracefully
        # degrading to null when its target is deleted. "At least one
        # relation on creation" is now an application/form-layer rule
        # (to be enforced by Activity's create view in Phase 4), not a
        # DB one — this documents that the DB itself no longer rejects
        # a fully unrelated Activity.
        activity = Activity.objects.create(
            activity_type=Activity.ActivityType.NOTE,
            subject="Orphan note",
            created_by=self.creator,
        )
        self.assertIsNone(activity.company)
        self.assertIsNone(activity.contact)
        self.assertIsNone(activity.lead)
        self.assertIsNone(activity.deal)

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

    def test_company_deletion_sets_activity_relation_null_not_cascade(self):
        # Regression test for docs/DATABASE_REVIEW.md finding #2: this
        # used to be CASCADE, which meant a single-tagged Activity was
        # destroyed with its Company. Now SET_NULL — the Activity (a
        # historical record) survives, just loses that one relation.
        activity = Activity.objects.create(
            activity_type=Activity.ActivityType.NOTE,
            subject="Note about Acme",
            company=self.company,
            created_by=self.creator,
        )
        self.company.delete()
        activity.refresh_from_db()
        self.assertIsNone(activity.company)

    def test_multi_tagged_activity_survives_deleting_one_of_its_relations(self):
        # The original bug this fix addresses: an Activity tagged to
        # both a Company and a Deal used to be destroyed entirely if
        # only the Deal was deleted, even though the Company (and the
        # Activity's relevance to it) was untouched.
        deal = Deal.objects.create(title="Acme deal", company=self.company, created_by=self.creator)
        activity = Activity.objects.create(
            activity_type=Activity.ActivityType.CALL,
            subject="Call about the deal",
            company=self.company,
            deal=deal,
            created_by=self.creator,
        )
        deal.delete()
        activity.refresh_from_db()
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())
        self.assertTrue(Activity.objects.filter(pk=activity.pk).exists())
        self.assertIsNone(activity.deal)
        self.assertEqual(activity.company, self.company)

    def test_activity_can_end_up_with_no_relations_after_full_degradation(self):
        activity = Activity.objects.create(
            activity_type=Activity.ActivityType.NOTE,
            subject="Only tied to the company",
            company=self.company,
            created_by=self.creator,
        )
        self.company.delete()
        activity.refresh_from_db()
        self.assertTrue(Activity.objects.filter(pk=activity.pk).exists())
        self.assertIsNone(activity.company)

    def test_existing_activity_cannot_be_saved_again(self):
        # docs/DATABASE_REVIEW.md finding #7: Activity is documented as
        # immutable history, but was previously only protected by
        # ActivityAdmin.has_change_permission — a plain .save() on an
        # existing instance succeeded silently. Now enforced in the
        # model itself.
        activity = Activity.objects.create(
            activity_type=Activity.ActivityType.NOTE,
            subject="Original",
            company=self.company,
            created_by=self.creator,
        )
        activity.subject = "Edited"
        with self.assertRaises(ValueError):
            activity.save()

        activity.refresh_from_db()
        self.assertEqual(activity.subject, "Original")

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
