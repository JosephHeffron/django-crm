from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from apps.crm.models import Activity, Company, Contact, Deal, Lead

User = get_user_model()


class ActivityListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:activity_list"))
        self.assertEqual(response.status_code, 302)

    def test_empty_list_shows_no_activities_message(self):
        response = self.client.get(reverse("crm:activity_list"))
        self.assertContains(response, "No activities found")

    def test_list_shows_activities(self):
        Activity.objects.create(
            activity_type=Activity.ActivityType.CALL,
            subject="Intro call",
            company=self.company,
            created_by=self.user,
        )
        response = self.client.get(reverse("crm:activity_list"))
        self.assertContains(response, "Intro call")

    def test_type_filter(self):
        Activity.objects.create(
            activity_type=Activity.ActivityType.CALL,
            subject="A call",
            company=self.company,
            created_by=self.user,
        )
        Activity.objects.create(
            activity_type=Activity.ActivityType.NOTE,
            subject="A note",
            company=self.company,
            created_by=self.user,
        )

        response = self.client.get(reverse("crm:activity_list"), {"type": "call"})
        subjects = [a.subject for a in response.context["activities"]]
        self.assertEqual(subjects, ["A call"])

    def test_invalid_type_param_is_ignored(self):
        Activity.objects.create(
            activity_type=Activity.ActivityType.NOTE,
            subject="A note",
            company=self.company,
            created_by=self.user,
        )
        response = self.client.get(reverse("crm:activity_list"), {"type": "not-a-real-type"})
        self.assertEqual(response.status_code, 200)
        subjects = [a.subject for a in response.context["activities"]]
        self.assertEqual(subjects, ["A note"])


class ActivityCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)
        self.contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.user
        )
        self.lead = Lead.objects.create(name="Jane Prospect", created_by=self.user)
        self.deal = Deal.objects.create(
            title="Acme deal", company=self.company, created_by=self.user
        )

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:activity_create"))
        self.assertEqual(response.status_code, 302)

    def test_get_prefills_relation_from_query_param(self):
        response = self.client.get(reverse("crm:activity_create"), {"company": self.company.pk})
        self.assertEqual(response.context["form"].initial.get("company"), self.company.pk)

    def test_get_with_invalid_query_param_does_not_error(self):
        response = self.client.get(reverse("crm:activity_create"), {"company": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("company", response.context["form"].initial)

    def test_create_sets_created_by(self):
        response = self.client.post(
            reverse("crm:activity_create"),
            {"activity_type": "call", "subject": "Intro call", "company": self.company.pk},
        )
        activity = Activity.objects.get(subject="Intro call")
        self.assertRedirects(response, self.company.get_absolute_url())
        self.assertEqual(activity.created_by, self.user)

    def test_create_without_any_relation_is_rejected(self):
        response = self.client.post(
            reverse("crm:activity_create"), {"activity_type": "note", "subject": "Orphan"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Activity.objects.exists())
        self.assertTrue(response.context["form"].non_field_errors())

    def test_redirect_prioritizes_company_over_other_relations(self):
        response = self.client.post(
            reverse("crm:activity_create"),
            {
                "activity_type": "meeting",
                "subject": "Joint meeting",
                "company": self.company.pk,
                "contact": self.contact.pk,
            },
        )
        self.assertRedirects(response, self.company.get_absolute_url())

    def test_redirect_falls_back_to_contact_when_no_company(self):
        response = self.client.post(
            reverse("crm:activity_create"),
            {"activity_type": "email", "subject": "Follow-up", "contact": self.contact.pk},
        )
        self.assertRedirects(response, self.contact.get_absolute_url())

    def test_redirect_falls_back_to_lead(self):
        response = self.client.post(
            reverse("crm:activity_create"),
            {"activity_type": "call", "subject": "Cold call", "lead": self.lead.pk},
        )
        self.assertRedirects(response, self.lead.get_absolute_url())

    def test_redirect_falls_back_to_deal(self):
        response = self.client.post(
            reverse("crm:activity_create"),
            {"activity_type": "note", "subject": "Deal note", "deal": self.deal.pk},
        )
        self.assertRedirects(response, self.deal.get_absolute_url())

    def test_no_activity_update_url_exists(self):
        # Activity is immutable (Activity.save() rejects updates) — no
        # edit view/URL should exist to invite trying.
        with self.assertRaises(NoReverseMatch):
            reverse("crm:activity_update", kwargs={"pk": 1})


class ActivityTimelineOnDetailPagesTests(TestCase):
    """The reusable timeline (crm/_activity_timeline.html) appears on
    Company/Contact/Lead/Deal detail pages, each linking to
    activity_create with the right relation pre-selected."""

    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)
        self.contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.user
        )
        self.lead = Lead.objects.create(name="Jane Prospect", created_by=self.user)
        self.deal = Deal.objects.create(
            title="Acme deal", company=self.company, created_by=self.user
        )

    def test_company_detail_shows_timeline_and_log_link(self):
        Activity.objects.create(
            activity_type=Activity.ActivityType.NOTE,
            subject="Company note",
            company=self.company,
            created_by=self.user,
        )
        response = self.client.get(self.company.get_absolute_url())
        self.assertContains(response, "Company note")
        self.assertContains(response, f"{reverse('crm:activity_create')}?company={self.company.pk}")

    def test_contact_detail_shows_timeline_and_log_link(self):
        Activity.objects.create(
            activity_type=Activity.ActivityType.EMAIL,
            subject="Contact email",
            contact=self.contact,
            created_by=self.user,
        )
        response = self.client.get(self.contact.get_absolute_url())
        self.assertContains(response, "Contact email")
        self.assertContains(response, f"{reverse('crm:activity_create')}?contact={self.contact.pk}")

    def test_lead_detail_shows_timeline_and_log_link(self):
        Activity.objects.create(
            activity_type=Activity.ActivityType.CALL,
            subject="Lead call",
            lead=self.lead,
            created_by=self.user,
        )
        response = self.client.get(self.lead.get_absolute_url())
        self.assertContains(response, "Lead call")
        self.assertContains(response, f"{reverse('crm:activity_create')}?lead={self.lead.pk}")

    def test_deal_detail_shows_timeline_and_log_link(self):
        Activity.objects.create(
            activity_type=Activity.ActivityType.MEETING,
            subject="Deal meeting",
            deal=self.deal,
            created_by=self.user,
        )
        response = self.client.get(self.deal.get_absolute_url())
        self.assertContains(response, "Deal meeting")
        self.assertContains(response, f"{reverse('crm:activity_create')}?deal={self.deal.pk}")

    def test_empty_timeline_shows_placeholder(self):
        response = self.client.get(self.company.get_absolute_url())
        self.assertContains(response, "No activity yet")
