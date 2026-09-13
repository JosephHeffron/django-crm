from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.crm.models import Company, Contact, Deal, Lead, Task

User = get_user_model()


class SearchViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("core:search"))
        self.assertEqual(response.status_code, 302)

    def test_no_query_shows_the_search_form_without_results(self):
        response = self.client.get(reverse("core:search"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "No results found")

    def test_finds_matching_company(self):
        Company.objects.create(name="Acme Rocket Corp", created_by=self.user)
        Company.objects.create(name="Globex Inc", created_by=self.user)
        response = self.client.get(reverse("core:search"), {"q": "Rocket"})
        self.assertContains(response, "Acme Rocket Corp")
        self.assertNotContains(response, "Globex Inc")

    def test_search_is_case_insensitive(self):
        Company.objects.create(name="Acme Rocket Corp", created_by=self.user)
        response = self.client.get(reverse("core:search"), {"q": "rocket"})
        self.assertContains(response, "Acme Rocket Corp")

    def test_finds_matching_contact_by_email(self):
        Contact.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com", created_by=self.user
        )
        response = self.client.get(reverse("core:search"), {"q": "ada@example.com"})
        self.assertContains(response, "Ada Lovelace")

    def test_finds_matching_lead_by_company_name(self):
        Lead.objects.create(name="Jane Prospect", company_name="Wonderco", created_by=self.user)
        response = self.client.get(reverse("core:search"), {"q": "Wonderco"})
        self.assertContains(response, "Jane Prospect")

    def test_finds_matching_deal(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        Deal.objects.create(title="Acme renewal deal", company=company, created_by=self.user)
        response = self.client.get(reverse("core:search"), {"q": "renewal"})
        self.assertContains(response, "Acme renewal deal")

    def test_finds_matching_task(self):
        Task.objects.create(title="Call about renewal", assigned_to=self.user, created_by=self.user)
        response = self.client.get(reverse("core:search"), {"q": "renewal"})
        self.assertContains(response, "Call about renewal")

    def test_no_matches_shows_no_results_message(self):
        response = self.client.get(reverse("core:search"), {"q": "zzz-nonexistent-zzz"})
        self.assertContains(response, "No results found")

    def test_results_are_capped_per_model(self):
        for i in range(25):
            Company.objects.create(name=f"CapTest {i}", created_by=self.user)
        response = self.client.get(reverse("core:search"), {"q": "CapTest"})
        self.assertEqual(response.content.decode().count("<li><a href="), 20)

    def test_tied_results_are_ordered_by_pk_as_a_tiebreaker(self):
        # These tasks all tie on the sort key Task.Meta.ordering alone
        # would use (due_date=None for every one). Without an explicit
        # "pk" tiebreaker in _search(), Postgres gives no guarantee
        # about their relative order, so which rows land inside the
        # [:20] cap — and in what order — could vary between requests.
        from apps.core.views import _search

        tasks = [
            Task.objects.create(title=f"TieTest {i}", assigned_to=self.user, created_by=self.user)
            for i in range(5)
        ]
        results = list(_search("TieTest")["tasks"])
        self.assertEqual([t.pk for t in results], sorted(t.pk for t in tasks))

    def test_activity_has_no_search_results_section(self):
        # Activity is deliberately out of scope (no detail page of its
        # own) — searching shouldn't surface an "Activities" section.
        response = self.client.get(reverse("core:search"), {"q": "anything"})
        self.assertNotContains(response, "<h2>Activities</h2>", html=True)
