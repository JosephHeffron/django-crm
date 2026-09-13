from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.crm.models import Company
from apps.crm.tests._helpers import grant_staff

User = get_user_model()


class CompanyListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
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
        grant_staff(self.user)
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
        grant_staff(self.user)
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
        grant_staff(self.user)
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


class CompanyDeactivateViewTests(TestCase):
    # docs/DATABASE_DESIGN.md: "companies are never hard-deleted from the
    # UI" — is_active is the documented soft-removal mechanism. An
    # earlier draft of this view actually called .delete(), which
    # contradicted that and also crashed (500) on any company with deal
    # history, since Deal.company is on_delete=PROTECT. Caught by
    # automated review before merge.

    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(
            reverse("crm:company_deactivate", kwargs={"pk": self.company.pk})
        )
        self.assertEqual(response.status_code, 302)

    def test_get_shows_confirmation_page(self):
        response = self.client.get(
            reverse("crm:company_deactivate", kwargs={"pk": self.company.pk})
        )
        self.assertContains(response, "Deactivate Acme Corp")

    def test_post_deactivates_without_deleting(self):
        response = self.client.post(
            reverse("crm:company_deactivate", kwargs={"pk": self.company.pk})
        )
        self.assertRedirects(response, self.company.get_absolute_url())
        self.company.refresh_from_db()
        self.assertFalse(self.company.is_active)
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

    def test_deactivating_a_company_with_deals_does_not_error(self):
        # Unlike a real delete, this never touches Deal.company's
        # on_delete=PROTECT constraint — no exception, no special
        # handling needed.
        from apps.crm.models import Deal

        Deal.objects.create(title="Acme deal", company=self.company, created_by=self.user)

        response = self.client.post(
            reverse("crm:company_deactivate", kwargs={"pk": self.company.pk})
        )
        self.assertRedirects(response, self.company.get_absolute_url())
        self.company.refresh_from_db()
        self.assertFalse(self.company.is_active)

    def test_deactivate_link_hidden_once_already_inactive(self):
        self.company.is_active = False
        self.company.save(update_fields=["is_active"])
        response = self.client.get(self.company.get_absolute_url())
        deactivate_url = reverse("crm:company_deactivate", kwargs={"pk": self.company.pk})
        self.assertNotContains(response, deactivate_url)
