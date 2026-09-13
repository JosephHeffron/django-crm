"""Tests for the role/permission model added in Phase 6 unit 2.

See docs/PERMISSIONS.md for the design. These tests exist alongside
(not instead of) the grant_staff()-equipped tests in the other
test_*_views.py files — those exercise normal CRUD behavior for a
Staff-group user; these specifically exercise the permission boundary
itself: a plain logged-in user with no group, a Staff-group member,
and a superuser.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.crm.models import Company, Contact, Deal, Lead, Task

User = get_user_model()


class StaffGroupSeedTests(TestCase):
    def test_staff_group_exists_with_expected_permissions(self):
        group = Group.objects.get(name="Staff")
        codenames = sorted(p.codename for p in group.permissions.all())
        self.assertEqual(
            codenames,
            [
                "add_activity",
                "add_company",
                "add_contact",
                "add_deal",
                "add_lead",
                "add_task",
                "change_company",
                "change_contact",
                "change_deal",
                "change_lead",
                "change_task",
            ],
        )


class ReadOnlyUserCanStillViewEverythingTests(TestCase):
    """A logged-in user with no group is the implicit "read-only" tier
    (docs/PERMISSIONS.md) — visibility isn't restricted, only writes."""

    def setUp(self):
        self.user = User.objects.create_user("bob", password="correct-horse-battery")
        self.client.login(username="bob", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)

    def test_can_view_company_list_and_detail(self):
        self.assertEqual(self.client.get(reverse("crm:company_list")).status_code, 200)
        self.assertEqual(self.client.get(self.company.get_absolute_url()).status_code, 200)

    def test_can_view_dashboard_and_search(self):
        self.assertEqual(self.client.get(reverse("core:index")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:search")).status_code, 200)


class NonStaffUserIsForbiddenFromMutatingViewsTests(TestCase):
    """A logged-in user with no permissions gets 403 on every
    create/edit/deactivate/complete/convert view."""

    def setUp(self):
        self.user = User.objects.create_user("bob", password="correct-horse-battery")
        self.client.login(username="bob", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)
        self.contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.user
        )
        self.lead = Lead.objects.create(name="Jane Prospect", created_by=self.user)
        self.deal = Deal.objects.create(
            title="Acme deal", company=self.company, created_by=self.user
        )
        self.task = Task.objects.create(
            title="Follow up", assigned_to=self.user, created_by=self.user
        )

    def test_company_create_forbidden(self):
        response = self.client.get(reverse("crm:company_create"))
        self.assertEqual(response.status_code, 403)

    def test_company_update_forbidden(self):
        response = self.client.get(reverse("crm:company_update", args=[self.company.pk]))
        self.assertEqual(response.status_code, 403)

    def test_company_deactivate_forbidden(self):
        response = self.client.post(reverse("crm:company_deactivate", args=[self.company.pk]))
        self.assertEqual(response.status_code, 403)
        self.company.refresh_from_db()
        self.assertTrue(self.company.is_active)

    def test_company_deactivate_confirmation_page_also_forbidden(self):
        # PermissionRequiredMixin.dispatch() gates every HTTP method
        # uniformly, so the GET confirmation page is blocked too, not
        # just the POST that actually deactivates.
        response = self.client.get(reverse("crm:company_deactivate", args=[self.company.pk]))
        self.assertEqual(response.status_code, 403)

    def test_contact_create_forbidden(self):
        response = self.client.get(reverse("crm:contact_create"))
        self.assertEqual(response.status_code, 403)

    def test_contact_update_forbidden(self):
        response = self.client.get(reverse("crm:contact_update", args=[self.contact.pk]))
        self.assertEqual(response.status_code, 403)

    def test_contact_deactivate_forbidden(self):
        response = self.client.post(reverse("crm:contact_deactivate", args=[self.contact.pk]))
        self.assertEqual(response.status_code, 403)

    def test_lead_create_forbidden(self):
        response = self.client.get(reverse("crm:lead_create"))
        self.assertEqual(response.status_code, 403)

    def test_lead_update_forbidden(self):
        response = self.client.get(reverse("crm:lead_update", args=[self.lead.pk]))
        self.assertEqual(response.status_code, 403)

    def test_lead_convert_forbidden(self):
        response = self.client.get(reverse("crm:lead_convert", args=[self.lead.pk]))
        self.assertEqual(response.status_code, 403)

    def test_deal_create_forbidden(self):
        response = self.client.get(reverse("crm:deal_create"))
        self.assertEqual(response.status_code, 403)

    def test_deal_update_forbidden(self):
        response = self.client.get(reverse("crm:deal_update", args=[self.deal.pk]))
        self.assertEqual(response.status_code, 403)

    def test_task_create_forbidden(self):
        response = self.client.get(reverse("crm:task_create"))
        self.assertEqual(response.status_code, 403)

    def test_task_update_forbidden(self):
        response = self.client.get(reverse("crm:task_update", args=[self.task.pk]))
        self.assertEqual(response.status_code, 403)

    def test_task_complete_forbidden(self):
        response = self.client.post(reverse("crm:task_complete", args=[self.task.pk]))
        self.assertEqual(response.status_code, 403)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.PENDING)

    def test_activity_create_forbidden(self):
        response = self.client.get(reverse("crm:activity_create"))
        self.assertEqual(response.status_code, 403)


class LeadConvertRequiresBothPermissionsTests(TestCase):
    """LeadConvertView needs crm.change_lead AND crm.add_contact —
    holding only one isn't enough (docs/PERMISSIONS.md)."""

    def setUp(self):
        self.user = User.objects.create_user("bob", password="correct-horse-battery")
        self.client.login(username="bob", password="correct-horse-battery")
        self.lead = Lead.objects.create(name="Jane Prospect", created_by=self.user)

    def test_change_lead_alone_is_not_enough(self):
        from django.contrib.auth.models import Permission

        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="crm", codename="change_lead")
        )
        response = self.client.get(reverse("crm:lead_convert", args=[self.lead.pk]))
        self.assertEqual(response.status_code, 403)

    def test_add_contact_alone_is_not_enough(self):
        from django.contrib.auth.models import Permission

        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="crm", codename="add_contact")
        )
        response = self.client.get(reverse("crm:lead_convert", args=[self.lead.pk]))
        self.assertEqual(response.status_code, 403)

    def test_both_permissions_together_are_sufficient(self):
        self.user.groups.add(Group.objects.get(name="Staff"))
        response = self.client.get(reverse("crm:lead_convert", args=[self.lead.pk]))
        self.assertEqual(response.status_code, 200)


class SuperuserBypassesPermissionChecksTests(TestCase):
    """Django's own built-in behavior — has_perm() always returns True
    for a superuser — verified here rather than just assumed."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            "admin", email="admin@example.com", password="correct-horse-battery"
        )
        self.client.login(username="admin", password="correct-horse-battery")

    def test_superuser_can_create_a_company_without_being_in_staff(self):
        self.assertFalse(self.user.groups.filter(name="Staff").exists())
        response = self.client.get(reverse("crm:company_create"))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_convert_a_lead_without_being_in_staff(self):
        lead = Lead.objects.create(name="Jane Prospect", created_by=self.user)
        response = self.client.get(reverse("crm:lead_convert", args=[lead.pk]))
        self.assertEqual(response.status_code, 200)
