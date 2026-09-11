from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.crm.models import Company

User = get_user_model()


class CompanyListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:company_list"))
        self.assertEqual(response.status_code, 302)

    def test_empty_list_shows_no_companies_message(self):
        response = self.client.get(reverse("crm:company_list"))
        self.assertContains(response, "No companies found")

    def test_list_shows_companies(self):
        Company.objects.create(name="Acme Corp", created_by=self.user)
        response = self.client.get(reverse("crm:company_list"))
        self.assertContains(response, "Acme Corp")

    def test_search_filters_by_name(self):
        Company.objects.create(name="Acme Corp", created_by=self.user)
        Company.objects.create(name="Globex Inc", created_by=self.user)

        response = self.client.get(reverse("crm:company_list"), {"q": "Acme"})
        self.assertContains(response, "Acme Corp")
        self.assertNotContains(response, "Globex Inc")

    def test_search_with_no_matches(self):
        Company.objects.create(name="Acme Corp", created_by=self.user)
        response = self.client.get(reverse("crm:company_list"), {"q": "Nonexistent"})
        self.assertContains(response, "No companies found")

    def test_status_filter_active_only(self):
        Company.objects.create(name="Active Co", created_by=self.user, is_active=True)
        Company.objects.create(name="Inactive Co", created_by=self.user, is_active=False)

        response = self.client.get(reverse("crm:company_list"), {"status": "active"})
        self.assertContains(response, "Active Co")
        self.assertNotContains(response, "Inactive Co")

    def test_status_filter_inactive_only(self):
        Company.objects.create(name="Active Co", created_by=self.user, is_active=True)
        Company.objects.create(name="Inactive Co", created_by=self.user, is_active=False)

        response = self.client.get(reverse("crm:company_list"), {"status": "inactive"})
        self.assertContains(response, "Inactive Co")
        self.assertNotContains(response, "Active Co")

    def test_pagination(self):
        for i in range(30):
            Company.objects.create(name=f"Company {i:02d}", created_by=self.user)

        response = self.client.get(reverse("crm:company_list"))
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(len(response.context["companies"]), 25)

        response = self.client.get(reverse("crm:company_list"), {"page": 2})
        self.assertEqual(len(response.context["companies"]), 5)


class CompanyDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(self.company.get_absolute_url())
        self.assertEqual(response.status_code, 302)

    def test_detail_shows_company_fields(self):
        response = self.client.get(self.company.get_absolute_url())
        self.assertContains(response, "Acme Corp")

    def test_detail_shows_related_contacts(self):
        from apps.crm.models import Contact

        Contact.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            created_by=self.user,
        )
        response = self.client.get(self.company.get_absolute_url())
        self.assertContains(response, "Ada Lovelace")

    def test_detail_shows_related_deals(self):
        from apps.crm.models import Deal

        Deal.objects.create(title="Acme deal", company=self.company, created_by=self.user)
        response = self.client.get(self.company.get_absolute_url())
        self.assertContains(response, "Acme deal")

    def test_nonexistent_company_returns_404(self):
        response = self.client.get(reverse("crm:company_detail", kwargs={"pk": 999999}))
        self.assertEqual(response.status_code, 404)


class CompanyCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:company_create"))
        self.assertEqual(response.status_code, 302)

    def test_get_shows_the_form(self):
        response = self.client.get(reverse("crm:company_create"))
        self.assertEqual(response.status_code, 200)

    def test_successful_create_sets_created_by(self):
        response = self.client.post(
            reverse("crm:company_create"), {"name": "Acme Corp", "is_active": "on"}
        )
        company = Company.objects.get(name="Acme Corp")
        self.assertRedirects(response, company.get_absolute_url())
        self.assertEqual(company.created_by, self.user)

    def test_missing_required_field_does_not_create(self):
        response = self.client.post(reverse("crm:company_create"), {"name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Company.objects.exists())
        self.assertTrue(response.context["form"].errors)


class CompanyUpdateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:company_update", kwargs={"pk": self.company.pk}))
        self.assertEqual(response.status_code, 302)

    def test_get_shows_prefilled_form(self):
        response = self.client.get(reverse("crm:company_update", kwargs={"pk": self.company.pk}))
        self.assertContains(response, "Acme Corp")

    def test_successful_update(self):
        response = self.client.post(
            reverse("crm:company_update", kwargs={"pk": self.company.pk}),
            {"name": "Acme Corporation", "is_active": "on"},
        )
        self.company.refresh_from_db()
        self.assertRedirects(response, self.company.get_absolute_url())
        self.assertEqual(self.company.name, "Acme Corporation")

    def test_update_preserves_created_by(self):
        self.client.post(
            reverse("crm:company_update", kwargs={"pk": self.company.pk}),
            {"name": "Acme Corporation", "is_active": "on"},
        )
        self.company.refresh_from_db()
        self.assertEqual(self.company.created_by, self.user)


class CompanyDeleteViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:company_delete", kwargs={"pk": self.company.pk}))
        self.assertEqual(response.status_code, 302)

    def test_get_shows_confirmation_page(self):
        response = self.client.get(reverse("crm:company_delete", kwargs={"pk": self.company.pk}))
        self.assertContains(response, "Delete Acme Corp")

    def test_post_deletes_the_company(self):
        response = self.client.post(reverse("crm:company_delete", kwargs={"pk": self.company.pk}))
        self.assertRedirects(response, reverse("crm:company_list"))
        self.assertFalse(Company.objects.filter(pk=self.company.pk).exists())

    def test_delete_view_handles_protected_company_gracefully(self):
        # Regression test: Deal.company uses on_delete=PROTECT
        # (docs/DATABASE_DESIGN.md finding #6), so deleting a company
        # with any deal history raises ProtectedError. Discovered via
        # manual smoke test: unhandled, this was a 500, not a friendly
        # error — the view now catches it and redirects back with a
        # message instead.
        from apps.crm.models import Deal

        Deal.objects.create(title="Acme deal", company=self.company, created_by=self.user)

        response = self.client.post(reverse("crm:company_delete", kwargs={"pk": self.company.pk}))

        # fetch_redirect_response=False: Django messages are one-time-read
        # (cookie-based), and assertRedirects' own default follow-up fetch
        # would otherwise consume the message before we get to check it.
        self.assertRedirects(
            response, self.company.get_absolute_url(), fetch_redirect_response=False
        )
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

        follow_response = self.client.get(response.url)
        self.assertContains(follow_response, "still has deals on record")
