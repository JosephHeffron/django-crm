from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Company, Contact, Deal, Task

User = get_user_model()


class DealListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:deal_list"))
        self.assertEqual(response.status_code, 302)

    def test_empty_list_shows_no_deals_message(self):
        response = self.client.get(reverse("crm:deal_list"))
        self.assertContains(response, "No deals found")

    def test_list_shows_deals(self):
        Deal.objects.create(title="Acme deal", company=self.company, created_by=self.user)
        response = self.client.get(reverse("crm:deal_list"))
        self.assertContains(response, "Acme deal")

    def test_search_matches_title(self):
        Deal.objects.create(title="Acme deal", company=self.company, created_by=self.user)
        Deal.objects.create(title="Globex deal", company=self.company, created_by=self.user)

        response = self.client.get(reverse("crm:deal_list"), {"q": "Acme"})
        titles = [d.title for d in response.context["deals"]]
        self.assertEqual(titles, ["Acme deal"])

    def test_stage_filter(self):
        Deal.objects.create(
            title="Early deal",
            company=self.company,
            stage=Deal.Stage.PROSPECTING,
            created_by=self.user,
        )
        Deal.objects.create(
            title="Late deal",
            company=self.company,
            stage=Deal.Stage.NEGOTIATION,
            created_by=self.user,
        )

        response = self.client.get(reverse("crm:deal_list"), {"stage": "negotiation"})
        titles = [d.title for d in response.context["deals"]]
        self.assertEqual(titles, ["Late deal"])

    def test_invalid_stage_param_is_ignored(self):
        Deal.objects.create(title="Some deal", company=self.company, created_by=self.user)
        response = self.client.get(reverse("crm:deal_list"), {"stage": "not-a-real-stage"})
        self.assertEqual(response.status_code, 200)
        titles = [d.title for d in response.context["deals"]]
        self.assertEqual(titles, ["Some deal"])

    def test_open_only_filter_excludes_closed_deals(self):
        Deal.objects.create(
            title="Open deal",
            company=self.company,
            stage=Deal.Stage.PROSPECTING,
            created_by=self.user,
        )
        Deal.objects.create(
            title="Won deal",
            company=self.company,
            stage=Deal.Stage.CLOSED_WON,
            created_by=self.user,
        )
        Deal.objects.create(
            title="Lost deal",
            company=self.company,
            stage=Deal.Stage.CLOSED_LOST,
            created_by=self.user,
        )

        response = self.client.get(reverse("crm:deal_list"), {"open": "1"})
        titles = {d.title for d in response.context["deals"]}
        self.assertEqual(titles, {"Open deal"})


class DealDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)
        self.deal = Deal.objects.create(
            title="Acme deal", company=self.company, created_by=self.user
        )

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(self.deal.get_absolute_url())
        self.assertEqual(response.status_code, 302)

    def test_detail_shows_deal_fields(self):
        response = self.client.get(self.deal.get_absolute_url())
        self.assertContains(response, "Acme deal")
        self.assertContains(response, "Acme Corp")

    def test_detail_shows_related_tasks(self):
        Task.objects.create(
            title="Follow up", assigned_to=self.user, deal=self.deal, created_by=self.user
        )
        response = self.client.get(self.deal.get_absolute_url())
        self.assertContains(response, "Follow up")

    def test_nonexistent_deal_returns_404(self):
        response = self.client.get(reverse("crm:deal_detail", kwargs={"pk": 999999}))
        self.assertEqual(response.status_code, 404)


class DealCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)
        self.contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.user
        )

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:deal_create"))
        self.assertEqual(response.status_code, 302)

    def test_create_with_company_only(self):
        response = self.client.post(
            reverse("crm:deal_create"),
            {"title": "Acme deal", "company": self.company.pk, "stage": "prospecting"},
        )
        deal = Deal.objects.get(title="Acme deal")
        self.assertRedirects(response, deal.get_absolute_url())
        self.assertEqual(deal.created_by, self.user)
        self.assertIsNone(deal.contact)

    def test_create_with_contact_only(self):
        self.client.post(
            reverse("crm:deal_create"),
            {"title": "Ada deal", "contact": self.contact.pk, "stage": "prospecting"},
        )
        deal = Deal.objects.get(title="Ada deal")
        self.assertIsNone(deal.company)
        self.assertEqual(deal.contact, self.contact)

    def test_create_without_company_or_contact_is_rejected(self):
        # Regression-style test written proactively: mirrors Deal's own
        # deal_has_company_or_contact CheckConstraint at the form layer
        # (docs/DATABASE_DESIGN.md) — this should be a normal form
        # error, not an IntegrityError/500.
        response = self.client.post(
            reverse("crm:deal_create"), {"title": "Orphan deal", "stage": "prospecting"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Deal.objects.exists())
        self.assertTrue(response.context["form"].non_field_errors())

    def test_create_with_probability_above_100_is_rejected(self):
        response = self.client.post(
            reverse("crm:deal_create"),
            {
                "title": "Bad prob deal",
                "company": self.company.pk,
                "stage": "prospecting",
                "probability": "150",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Deal.objects.exists())

    def test_create_in_a_closed_stage_sets_closed_at(self):
        response = self.client.post(
            reverse("crm:deal_create"),
            {"title": "Fast deal", "company": self.company.pk, "stage": "closed_won"},
        )
        deal = Deal.objects.get(title="Fast deal")
        self.assertRedirects(response, deal.get_absolute_url())
        self.assertIsNotNone(deal.closed_at)

    def test_create_in_an_open_stage_leaves_closed_at_unset(self):
        self.client.post(
            reverse("crm:deal_create"),
            {"title": "Slow deal", "company": self.company.pk, "stage": "prospecting"},
        )
        deal = Deal.objects.get(title="Slow deal")
        self.assertIsNone(deal.closed_at)


class DealUpdateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)
        self.deal = Deal.objects.create(
            title="Acme deal",
            company=self.company,
            stage=Deal.Stage.PROSPECTING,
            created_by=self.user,
        )

    def test_successful_update(self):
        response = self.client.post(
            reverse("crm:deal_update", kwargs={"pk": self.deal.pk}),
            {"title": "Acme deal v2", "company": self.company.pk, "stage": "proposal"},
        )
        self.deal.refresh_from_db()
        self.assertRedirects(response, self.deal.get_absolute_url())
        self.assertEqual(self.deal.title, "Acme deal v2")
        self.assertEqual(self.deal.stage, Deal.Stage.PROPOSAL)

    def test_moving_to_a_closed_stage_sets_closed_at(self):
        self.assertIsNone(self.deal.closed_at)
        self.client.post(
            reverse("crm:deal_update", kwargs={"pk": self.deal.pk}),
            {"title": "Acme deal", "company": self.company.pk, "stage": "closed_won"},
        )
        self.deal.refresh_from_db()
        self.assertIsNotNone(self.deal.closed_at)

    def test_reopening_a_closed_deal_clears_closed_at(self):
        self.deal.stage = Deal.Stage.CLOSED_WON
        self.deal.closed_at = timezone.now()
        self.deal.save()

        self.client.post(
            reverse("crm:deal_update", kwargs={"pk": self.deal.pk}),
            {"title": "Acme deal", "company": self.company.pk, "stage": "negotiation"},
        )
        self.deal.refresh_from_db()
        self.assertIsNone(self.deal.closed_at)

    def test_staying_closed_does_not_change_the_original_closed_at(self):
        self.deal.stage = Deal.Stage.CLOSED_WON
        self.deal.closed_at = timezone.now() - timezone.timedelta(days=3)
        self.deal.save()
        original_closed_at = self.deal.closed_at

        self.client.post(
            reverse("crm:deal_update", kwargs={"pk": self.deal.pk}),
            {
                "title": "Acme deal",
                "company": self.company.pk,
                "stage": "closed_won",
                "notes": "updated notes",
            },
        )
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.closed_at, original_closed_at)

    def test_removing_both_company_and_contact_is_rejected(self):
        response = self.client.post(
            reverse("crm:deal_update", kwargs={"pk": self.deal.pk}),
            {"title": "Acme deal", "stage": "prospecting"},
        )
        self.assertEqual(response.status_code, 200)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.company, self.company)
