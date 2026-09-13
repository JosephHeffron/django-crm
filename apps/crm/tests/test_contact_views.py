from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.crm.models import Company, Contact, Deal, Task
from apps.crm.tests._helpers import grant_staff

User = get_user_model()


class ContactListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:contact_list"))
        self.assertEqual(response.status_code, 302)

    def test_empty_list_shows_no_contacts_message(self):
        response = self.client.get(reverse("crm:contact_list"))
        self.assertContains(response, "No contacts found")

    def test_list_shows_contacts(self):
        Contact.objects.create(first_name="Ada", last_name="Lovelace", created_by=self.user)
        response = self.client.get(reverse("crm:contact_list"))
        self.assertContains(response, "Ada")
        self.assertContains(response, "Lovelace")

    def test_search_matches_first_name_last_name_or_email(self):
        Contact.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            created_by=self.user,
        )
        Contact.objects.create(first_name="Grace", last_name="Hopper", created_by=self.user)

        response = self.client.get(reverse("crm:contact_list"), {"q": "Ada"})
        self.assertContains(response, "Lovelace")
        self.assertNotContains(response, "Hopper")

        response = self.client.get(reverse("crm:contact_list"), {"q": "example.com"})
        self.assertContains(response, "Lovelace")

    def test_status_filter(self):
        # Names deliberately don't contain "active"/"inactive" — those
        # words always appear in the filter <select> options regardless
        # of which contacts are shown, so asserting on them directly
        # would pass even if the filter did nothing.
        Contact.objects.create(
            first_name="Kept", last_name="Visible", created_by=self.user, is_active=True
        )
        Contact.objects.create(
            first_name="Hidden", last_name="Away", created_by=self.user, is_active=False
        )

        response = self.client.get(reverse("crm:contact_list"), {"status": "active"})
        self.assertContains(response, "Kept")
        self.assertNotContains(response, "Hidden")

    def test_company_filter(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        other_company = Company.objects.create(name="Globex Inc", created_by=self.user)
        Contact.objects.create(
            first_name="Ada", last_name="Lovelace", company=company, created_by=self.user
        )
        Contact.objects.create(
            first_name="Grace",
            last_name="Hopper",
            company=other_company,
            created_by=self.user,
        )

        response = self.client.get(reverse("crm:contact_list"), {"company": company.pk})
        self.assertContains(response, "Lovelace")
        self.assertNotContains(response, "Hopper")

    def test_company_filter_control_is_present_in_the_form(self):
        # Regression test: the queryset supported ?company= from the
        # start, but the filter form itself had no way to set it —
        # caught by review.
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        response = self.client.get(reverse("crm:contact_list"))
        self.assertContains(response, f'<option value="{company.pk}"')
        self.assertContains(response, "Acme Corp")

    def test_invalid_company_param_is_ignored_not_a_500(self):
        # Regression test: a non-numeric ?company= value reached
        # filter(company_id=...) directly and raised ValueError,
        # surfacing as an unhandled 500. Caught by review.
        Contact.objects.create(first_name="Ada", last_name="Lovelace", created_by=self.user)
        response = self.client.get(reverse("crm:contact_list"), {"company": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lovelace")

    def test_pagination(self):
        for i in range(30):
            Contact.objects.create(
                first_name=f"Person{i:02d}", last_name="Test", created_by=self.user
            )

        response = self.client.get(reverse("crm:contact_list"))
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(len(response.context["contacts"]), 25)

    def test_pagination_preserves_company_filter(self):
        # Regression test: pagination links carried q/status but not
        # company, so navigating pages dropped the company filter.
        # Caught by review.
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        other_company = Company.objects.create(name="Globex Inc", created_by=self.user)
        for i in range(30):
            Contact.objects.create(
                first_name=f"Person{i:02d}",
                last_name="Acme",
                company=company,
                created_by=self.user,
            )
        Contact.objects.create(
            first_name="Other", last_name="Globex", company=other_company, created_by=self.user
        )

        response = self.client.get(reverse("crm:contact_list"), {"company": company.pk})
        self.assertContains(response, f"company={company.pk}")

        page_2 = self.client.get(reverse("crm:contact_list"), {"company": company.pk, "page": 2})
        self.assertEqual(len(page_2.context["contacts"]), 5)
        self.assertTrue(all(c.company_id == company.pk for c in page_2.context["contacts"]))


class ContactDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.user
        )

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(self.contact.get_absolute_url())
        self.assertEqual(response.status_code, 302)

    def test_detail_shows_contact_fields(self):
        response = self.client.get(self.contact.get_absolute_url())
        self.assertContains(response, "Ada")
        self.assertContains(response, "Lovelace")

    def test_detail_shows_company_link(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        self.contact.company = company
        self.contact.save()
        response = self.client.get(self.contact.get_absolute_url())
        self.assertContains(response, "Acme Corp")

    def test_detail_shows_related_deals(self):
        Deal.objects.create(title="Acme deal", contact=self.contact, created_by=self.user)
        response = self.client.get(self.contact.get_absolute_url())
        self.assertContains(response, "Acme deal")

    def test_detail_shows_related_tasks(self):
        Task.objects.create(
            title="Follow up", assigned_to=self.user, contact=self.contact, created_by=self.user
        )
        response = self.client.get(self.contact.get_absolute_url())
        self.assertContains(response, "Follow up")

    def test_nonexistent_contact_returns_404(self):
        response = self.client.get(reverse("crm:contact_detail", kwargs={"pk": 999999}))
        self.assertEqual(response.status_code, 404)


class ContactCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:contact_create"))
        self.assertEqual(response.status_code, 302)

    def test_get_shows_the_form(self):
        response = self.client.get(reverse("crm:contact_create"))
        self.assertEqual(response.status_code, 200)

    def test_successful_create_sets_created_by(self):
        response = self.client.post(
            reverse("crm:contact_create"),
            {"first_name": "Ada", "last_name": "Lovelace", "is_active": "on"},
        )
        contact = Contact.objects.get(first_name="Ada")
        self.assertRedirects(response, contact.get_absolute_url())
        self.assertEqual(contact.created_by, self.user)

    def test_create_with_company(self):
        company = Company.objects.create(name="Acme Corp", created_by=self.user)
        self.client.post(
            reverse("crm:contact_create"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "company": company.pk,
                "is_active": "on",
            },
        )
        contact = Contact.objects.get(first_name="Ada")
        self.assertEqual(contact.company, company)

    def test_missing_required_field_does_not_create(self):
        response = self.client.post(
            reverse("crm:contact_create"), {"first_name": "", "last_name": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Contact.objects.exists())
        self.assertTrue(response.context["form"].errors)


class ContactUpdateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.user
        )

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:contact_update", kwargs={"pk": self.contact.pk}))
        self.assertEqual(response.status_code, 302)

    def test_get_shows_prefilled_form(self):
        response = self.client.get(reverse("crm:contact_update", kwargs={"pk": self.contact.pk}))
        self.assertContains(response, "Ada")

    def test_successful_update(self):
        response = self.client.post(
            reverse("crm:contact_update", kwargs={"pk": self.contact.pk}),
            {"first_name": "Ada", "last_name": "King", "is_active": "on"},
        )
        self.contact.refresh_from_db()
        self.assertRedirects(response, self.contact.get_absolute_url())
        self.assertEqual(self.contact.last_name, "King")

    def test_update_preserves_created_by(self):
        self.client.post(
            reverse("crm:contact_update", kwargs={"pk": self.contact.pk}),
            {"first_name": "Ada", "last_name": "King", "is_active": "on"},
        )
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.created_by, self.user)


class ContactDeactivateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_staff(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.user
        )

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(
            reverse("crm:contact_deactivate", kwargs={"pk": self.contact.pk})
        )
        self.assertEqual(response.status_code, 302)

    def test_get_shows_confirmation_page(self):
        response = self.client.get(
            reverse("crm:contact_deactivate", kwargs={"pk": self.contact.pk})
        )
        self.assertContains(response, "Deactivate Ada Lovelace")

    def test_post_deactivates_without_deleting(self):
        response = self.client.post(
            reverse("crm:contact_deactivate", kwargs={"pk": self.contact.pk})
        )
        self.assertRedirects(response, self.contact.get_absolute_url())
        self.contact.refresh_from_db()
        self.assertFalse(self.contact.is_active)
        self.assertTrue(Contact.objects.filter(pk=self.contact.pk).exists())

    def test_deactivate_link_hidden_once_already_inactive(self):
        self.contact.is_active = False
        self.contact.save(update_fields=["is_active"])
        response = self.client.get(self.contact.get_absolute_url())
        deactivate_url = reverse("crm:contact_deactivate", kwargs={"pk": self.contact.pk})
        self.assertNotContains(response, deactivate_url)
