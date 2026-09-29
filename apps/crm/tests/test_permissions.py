"""Role and permission boundaries — docs/decisions/0008-roles-and-row-level-scoping.md.

Two layers, tested separately:
1. Role (Owner / Sales Rep / Cleaner / no role) decides who may use a
   CRM page at all — enforced by SalesRoleRequiredMixin.
2. Model permissions still gate writes *within* an allowed role
   (PermissionRequiredMixin, kept as defense in depth) — e.g. if the
   Owner removes a permission from the Sales Rep group in the admin.
"""

import importlib

from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from apps.crm.models import Company, Contact, Deal, Lead, Task
from apps.crm.tests._helpers import grant_role
from apps.users.roles import Role

User = get_user_model()

SALES_PERMISSION_CODENAMES = [
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
]


def _login(client, username, role=None):
    user = User.objects.create_user(username, password="correct-horse-battery")
    if role is not None:
        grant_role(user, role)
    client.login(username=username, password="correct-horse-battery")
    return user


class RoleSeedTests(TestCase):
    def test_owner_and_sales_rep_hold_the_former_staff_permissions(self):
        # users/0004 adds field-service permissions on top (see
        # apps/jobs/tests/test_migrations.py::FieldServicePermissionSeedTests);
        # these must remain.
        for name in ("Owner", "Sales Rep"):
            group = Group.objects.get(name=name)
            codenames = set(group.permissions.values_list("codename", flat=True))
            self.assertTrue(set(SALES_PERMISSION_CODENAMES) <= codenames, name)

    def test_cleaner_cannot_write_customer_records(self):
        customer_models = ["company", "contact", "lead", "deal", "task", "activity"]
        codenames = set(
            Group.objects.get(name="Cleaner").permissions.values_list("codename", flat=True)
        )
        for model in customer_models:
            self.assertNotIn(f"add_{model}", codenames)
            self.assertNotIn(f"change_{model}", codenames)

    def test_staff_group_is_retired(self):
        self.assertFalse(Group.objects.filter(name="Staff").exists())


class RolesMigrationTests(TestCase):
    """Exercise users/0002_roles's forward and reverse functions directly
    against the real app registry (they only use apps.get_model)."""

    migration = importlib.import_module("apps.users.migrations.0002_roles")

    def test_forward_moves_staff_members_to_sales_rep(self):
        staff = Group.objects.create(name="Staff")
        member = User.objects.create_user("legacy")
        member.groups.add(staff)

        self.migration.create_roles(global_apps, None)

        self.assertFalse(Group.objects.filter(name="Staff").exists())
        self.assertTrue(member.groups.filter(name="Sales Rep").exists())

    def test_reverse_restores_staff_with_its_members_and_permissions(self):
        rep = User.objects.create_user("rep")
        grant_role(rep, Role.SALES_REP)

        self.migration.restore_staff(global_apps, None)

        staff = Group.objects.get(name="Staff")
        self.assertTrue(rep.groups.filter(name="Staff").exists())
        self.assertEqual(
            sorted(p.codename for p in staff.permissions.all()), SALES_PERMISSION_CODENAMES
        )
        self.assertFalse(Group.objects.filter(name__in=["Owner", "Sales Rep", "Cleaner"]).exists())


class NoRoleUserIsDeniedCrmPagesTests(TestCase):
    """Fail closed: an account nobody has assigned a role yet sees no
    customer data at all."""

    def setUp(self):
        self.user = _login(self.client, "newhire")
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)

    def test_crm_pages_are_forbidden(self):
        for url in [
            reverse("crm:company_list"),
            self.company.get_absolute_url(),
            reverse("crm:contact_list"),
            reverse("crm:task_list"),
            reverse("core:search"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_dashboard_explains_the_missing_role(self):
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No role assigned yet")
        self.assertNotContains(response, "Pipeline by stage")


class CleanerIsDeniedCustomerPagesTests(TestCase):
    """Cleaners never see the customer list, pipeline, or search —
    their scoped pages (schedule, jobs) arrive in Phase 17 unit 3."""

    def setUp(self):
        self.user = _login(self.client, "crew", Role.CLEANER)
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

    def test_read_pages_forbidden(self):
        for url in [
            reverse("crm:company_list"),
            reverse("crm:contact_list"),
            self.contact.get_absolute_url(),
            reverse("crm:lead_list"),
            reverse("crm:deal_list"),
            reverse("crm:activity_list"),
            reverse("crm:task_list"),
            reverse("core:search"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_mutating_views_forbidden(self):
        for method, url in [
            ("get", reverse("crm:company_create")),
            ("get", reverse("crm:company_update", args=[self.company.pk])),
            ("post", reverse("crm:company_deactivate", args=[self.company.pk])),
            ("get", reverse("crm:contact_create")),
            ("post", reverse("crm:contact_deactivate", args=[self.contact.pk])),
            ("get", reverse("crm:lead_convert", args=[self.lead.pk])),
            ("get", reverse("crm:deal_update", args=[self.deal.pk])),
            ("post", reverse("crm:task_complete", args=[self.task.pk])),
            ("get", reverse("crm:activity_create")),
        ]:
            self.assertEqual(getattr(self.client, method)(url).status_code, 403, url)
        self.company.refresh_from_db()
        self.assertTrue(self.company.is_active)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.PENDING)

    def test_dashboard_shows_the_cleaner_view(self):
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Coming up")
        self.assertNotContains(response, "Recent activity")
        self.assertNotContains(response, "Site visits")


class SalesAndOwnerRolesCanUseCrmTests(TestCase):
    def test_sales_rep_can_read_and_create(self):
        _login(self.client, "rep", Role.SALES_REP)
        self.assertEqual(self.client.get(reverse("crm:company_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("crm:company_create")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:search")).status_code, 200)

    def test_owner_group_member_can_read_and_create(self):
        _login(self.client, "boss", Role.OWNER)
        self.assertEqual(self.client.get(reverse("crm:contact_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("crm:contact_create")).status_code, 200)

    def test_sales_rep_sees_the_business_dashboard(self):
        _login(self.client, "rep", Role.SALES_REP)
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, "Site visits this week")
        self.assertContains(response, "Recent activity")


class WritePermissionsStillEnforcedWithinARoleTests(TestCase):
    """Defense in depth: if the Owner strips a permission from the Sales
    Rep group in the admin, the page stays usable but the write doesn't."""

    def setUp(self):
        self.user = _login(self.client, "rep", Role.SALES_REP)
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)

    def _revoke(self, codename):
        Group.objects.get(name="Sales Rep").permissions.remove(
            Permission.objects.get(content_type__app_label="crm", codename=codename)
        )

    def test_revoked_change_permission_blocks_editing_but_not_reading(self):
        self._revoke("change_company")
        self.assertEqual(self.client.get(reverse("crm:company_list")).status_code, 200)
        response = self.client.get(reverse("crm:company_update", args=[self.company.pk]))
        self.assertEqual(response.status_code, 403)


class LeadConvertRequiresBothPermissionsTests(TestCase):
    """LeadConvertView needs crm.change_lead AND crm.add_contact —
    holding only one isn't enough (docs/PERMISSIONS.md)."""

    def setUp(self):
        self.user = _login(self.client, "rep", Role.SALES_REP)
        self.lead = Lead.objects.create(name="Jane Prospect", created_by=self.user)
        self.group = Group.objects.get(name="Sales Rep")

    def _keep_only(self, codename):
        self.group.permissions.set(
            [Permission.objects.get(content_type__app_label="crm", codename=codename)]
        )

    def test_change_lead_alone_is_not_enough(self):
        self._keep_only("change_lead")
        response = self.client.get(reverse("crm:lead_convert", args=[self.lead.pk]))
        self.assertEqual(response.status_code, 403)

    def test_add_contact_alone_is_not_enough(self):
        self._keep_only("add_contact")
        response = self.client.get(reverse("crm:lead_convert", args=[self.lead.pk]))
        self.assertEqual(response.status_code, 403)

    def test_both_permissions_together_are_sufficient(self):
        response = self.client.get(reverse("crm:lead_convert", args=[self.lead.pk]))
        self.assertEqual(response.status_code, 200)


class SuperuserIsTreatedAsOwnerTests(TestCase):
    """A superuser is always the Owner role, with no group needed, and
    Django's has_perm() short-circuits for them — verified, not assumed."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            "admin", email="admin@example.com", password="correct-horse-battery"
        )
        self.client.login(username="admin", password="correct-horse-battery")

    def test_superuser_can_create_a_company_without_any_role_group(self):
        self.assertFalse(self.user.groups.exists())
        response = self.client.get(reverse("crm:company_create"))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_convert_a_lead(self):
        lead = Lead.objects.create(name="Jane Prospect", created_by=self.user)
        response = self.client.get(reverse("crm:lead_convert", args=[lead.pk]))
        self.assertEqual(response.status_code, 200)


class LegacyAdminIsReadOnlyTests(TestCase):
    """Lead and Deal were folded into Contact/Quote (jobs/0003); the
    admin keeps them visible but allows no add, change, or delete."""

    def test_no_add_change_or_delete(self):
        from django.contrib import admin
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = User.objects.create_superuser("root", "r@example.com", "pw")
        for model in (Lead, Deal):
            model_admin = admin.site._registry[model]
            self.assertFalse(model_admin.has_add_permission(request))
            self.assertFalse(model_admin.has_change_permission(request))
            self.assertFalse(model_admin.has_delete_permission(request))
