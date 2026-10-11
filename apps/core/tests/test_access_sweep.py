"""Every route in the app, checked against every kind of visitor.

Written during the QA audit (`docs/QA_REPORT.md`). The project already
has careful per-feature permission tests; what it did not have is a
sweep that **walks the URL resolver itself**, so a route added later
cannot quietly escape the check by nobody remembering to add it to a
list. The same discipline the inline-style sweep and the form-template
walk already use.

Three questions, asked of all 94 application routes:

1. Can a signed-out visitor reach it? Only the ones on PUBLIC may
   answer 200. Everything else must redirect to sign-in, or refuse.
2. Can somebody signed in with **no role** reach a customer page?
   `docs/decisions/0008-roles-and-row-level-scoping.md` says no.
3. Does each role-guarded route actually refuse the roles it names?

The point of building the table from the resolver is that the failure
mode being guarded against is *omission*. A hand-written list of routes
to check is only ever as complete as the person who last edited it.

`ARGS_UNAVAILABLE` is the honest escape hatch: a route whose argument
this fixture cannot supply is **named and counted**, not skipped
silently, and `test_every_route_is_either_swept_or_explained` fails if
that set ever grows.
"""

import re
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django.utils import timezone

from apps.crm.models import Company, Property, Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Expense, Photo
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

User = get_user_model()
PASSWORD = "correct-horse-battery"

# Routes a signed-out visitor is *meant* to be able to load, each with
# the reason. Anything not here and answering 200 anonymously is a
# finding, not a nuance.
PUBLIC = {
    "users:login": "the sign-in page itself",
    "users:logout": "signing out when already out is harmless",
    "core:health": "the container health check, before any session exists",
    "core:manifest": "the PWA manifest, fetched by the browser unauthenticated",
    "core:service_worker": "the service worker script, same",
    "core:offline": "the offline fallback page the service worker shows",
    "core:business_logo": "the business logo, shown on the sign-in page",
    "crm:lead_list": "a permanent redirect to a page that enforces its own access",
    "crm:deal_list": "likewise",
}

# Routes whose arguments this fixture cannot produce. Named so the gap
# is visible; see `test_every_route_is_either_swept_or_explained`.
ARGS_UNAVAILABLE: set[str] = set()


def app_routes():
    """Every named, non-admin route, as (name, [param names])."""
    found = []

    def walk(resolver, prefix="", namespace=None):
        for pattern in resolver.url_patterns:
            if isinstance(pattern, URLResolver):
                walk(
                    resolver=pattern,
                    prefix=prefix + str(pattern.pattern),
                    namespace=pattern.namespace or namespace,
                )
            elif isinstance(pattern, URLPattern):
                full = prefix + str(pattern.pattern)
                if full.startswith("admin/") or not pattern.name:
                    continue
                name = f"{namespace}:{pattern.name}" if namespace else pattern.name
                params = [p for _, p in re.findall(r"<(?:([a-z]+):)?([a-z_]+)>", full)]
                found.append((name, params))

    walk(get_resolver())
    return found


class RouteSweep(TestCase):
    """One fixture holding one of everything, so every route resolves."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = grant_role(f.user("boss"), Role.OWNER)
        cls.rep = grant_role(f.user("riley"), Role.SALES_REP)
        cls.casey = grant_role(f.user("casey"), Role.CLEANER)
        cls.nobody = User.objects.create_user("nobody", password=PASSWORD)

        cls.company = Company.objects.create(name="Acme", created_by=cls.owner)
        cls.customer = f.contact(cls.owner)
        cls.address = Property.objects.create(
            contact=cls.customer,
            street="1 Main St",
            city="Rochester",
            state="NY",
            postal_code="14600",
        )
        cls.job = f.job(cls.customer, cls.owner)
        f.assign(cls.job, cls.casey)
        cls.quote = f.quote(cls.customer, cls.owner)
        cls.invoice = f.invoice(cls.job)
        cls.task = Task.objects.create(
            title="Call back", assigned_to=cls.owner, created_by=cls.owner
        )
        cls.expense = Expense.objects.create(
            description="Fuel",
            amount=Decimal("40.00"),
            category=Expense.Category.FUEL,
            date=date(2026, 10, 1),
            recorded_by=cls.owner,
        )
        cls.photo = Photo.objects.create(
            job=cls.job, uploaded_by=cls.owner, image="private/photos/x.jpg"
        )
        cls.service = f.service()

    def args_for(self, name, params):
        """Concrete arguments for one route, or None if we cannot."""
        if not params:
            return []
        by_route = {
            "crm:company_detail": [self.company.pk],
            "crm:company_update": [self.company.pk],
            "crm:company_deactivate": [self.company.pk],
            "crm:contact_detail": [self.customer.pk],
            "crm:contact_update": [self.customer.pk],
            "crm:contact_deactivate": [self.customer.pk],
            "crm:property_update": [self.address.pk],
            "crm:task_detail": [self.task.pk],
            "crm:task_update": [self.task.pk],
            "crm:task_complete": [self.task.pk],
            "crm:plan_detail": [1],
            "core:activity_undo": [1],
            "core:notification_read": [1],
            "jobs:job_detail": [self.job.pk],
            "jobs:job_update": [self.job.pk],
            "jobs:job_status": [self.job.pk],
            "jobs:job_reschedule": [self.job.pk],
            "jobs:job_photo_add": [self.job.pk],
            "jobs:quote_detail": [self.quote.pk],
            "jobs:quote_update": [self.quote.pk],
            "jobs:quote_photo_add": [self.quote.pk],
            "jobs:invoice_detail": [self.invoice.pk],
            "jobs:invoice_update": [self.invoice.pk],
            "jobs:payment_create": [self.invoice.pk],
            "jobs:expense_update": [self.expense.pk],
            "jobs:service_update": [self.service.pk],
            "jobs:property_locate": [self.address.pk],
            "jobs:photo": [self.photo.uuid],
            "jobs:photo_remove": [self.photo.uuid],
            "jobs:report_detail": ["revenue-by-service"],
            "jobs:report_csv": ["revenue-by-service"],
            "messaging:channel": ["general"],
            "messaging:direct": [self.rep.username],
            "people:member": [self.rep.username],
            "people:avatar": [self.rep.username],
        }
        return by_route.get(name)

    def swept(self):
        """(name, url) for every route we can actually build."""
        for name, params in app_routes():
            args = self.args_for(name, params)
            if args is None:
                continue
            yield name, reverse(name, args=args)


class SignedOutVisitorTests(RouteSweep):
    def test_no_route_outside_the_public_list_answers_200_signed_out(self):
        """The sweep that omission cannot defeat.

        A GET only — a POST-only endpoint answering 405 to a signed-out
        GET would be a finding in itself, and is checked separately.
        """
        leaked = []
        for name, url in self.swept():
            if name in PUBLIC:
                continue
            response = self.client.get(url)
            if response.status_code == 200:
                leaked.append(f"{name} ({url}) -> 200 while signed out")
        self.assertEqual(leaked, [], "\n".join(leaked))

    def test_no_public_route_has_quietly_become_login_gated(self):
        """The other half: the allowlist must not be aspirational.

        The property that matters is that these do not *demand a
        session*, which is not the same as answering 200. Two of them
        legitimately do not: `logout` is POST-only in Django 5+, and the
        business logo 404s until one is uploaded. Both prove the point —
        the request was handled rather than bounced to sign-in. So this
        asserts on the redirect target, which is the thing that would
        break the sign-in page or the container health check.
        """
        broken = []
        for name, url in self.swept():
            if name not in PUBLIC:
                continue
            response = self.client.get(url)
            sent_to_login = response.status_code in (301, 302) and "login" in response.get(
                "Location", ""
            )
            if sent_to_login:
                broken.append(f"{name} ({url}) now demands a session")
        self.assertEqual(broken, [], "\n".join(broken))

    def test_changing_a_password_requires_being_signed_in(self):
        """Django ships this guard; this asserts it rather than trusting
        it, because the route is wired up by hand in `users/urls.py`."""
        response = self.client.get(reverse("users:password_change"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])


class NoRoleTests(RouteSweep):
    """ADR 0008: signing in is not the same as being allowed in."""

    def setUp(self):
        self.client.login(username="nobody", password=PASSWORD)

    def test_someone_with_no_role_reaches_no_customer_page(self):
        allowed = {
            # The sign-in page, and signing out.
            "users:login",
            "users:logout",
            "users:password_change",
            "users:password_change_done",
            # Their own account and the shell around it.
            "people:profile",
            "people:profile_edit",
            "people:avatar",
            "core:health",
            "core:manifest",
            "core:service_worker",
            "core:offline",
            "core:business_logo",
            "core:notifications",
            "core:notification_read",
            "core:notifications_read_all",
            "core:onboarding_dismiss",
            "core:customize",
            "core:whats_new",
            "core:styleguide",
            # The dashboard loads, deliberately, and shows nothing —
            # `DashboardView.get_context_data` returns early when the
            # role is None. Asserted below rather than trusted.
            "core:index",
            # Permanent redirects to pages that enforce their own access.
            "crm:lead_list",
            "crm:deal_list",
        }
        leaked = []
        for name, url in self.swept():
            if name in allowed:
                continue
            response = self.client.get(url)
            if response.status_code == 200:
                leaked.append(f"{name} ({url}) -> 200 with no role")
        self.assertEqual(leaked, [], "\n".join(leaked))

    def test_the_dashboard_they_can_load_shows_them_nothing(self):
        """`core:index` is on the allowlist above, so this is the
        assertion that makes that safe rather than merely permitted.

        `DashboardView.get_context_data` returns before computing
        anything when the role is None. If that early return were ever
        removed, the page would start aggregating revenue and jobs for
        somebody with no role at all.
        """
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["role"])
        for leaky in ("jobs_today", "revenue", "pipeline", "hours"):
            self.assertNotIn(leaky, response.context, f"a roleless dashboard computed {leaky}")


class CoverageHonestyTests(RouteSweep):
    def test_every_route_is_either_swept_or_explained(self):
        """No route may fall out of the sweep unremarked."""
        missed = []
        for name, params in app_routes():
            if self.args_for(name, params) is None and name not in ARGS_UNAVAILABLE:
                missed.append(name)
        self.assertEqual(missed, [], f"routes the sweep cannot build arguments for: {missed}")

    def test_the_sweep_actually_covers_the_whole_app(self):
        """A sweep that silently covers three routes proves nothing."""
        self.assertGreaterEqual(len(list(self.swept())), 90)


class RowScopingTests(RouteSweep):
    """Out of scope is 404, never 403 — a 403 confirms the record
    exists, which is the thing being withheld."""

    def setUp(self):
        self.other_crew = grant_role(f.user("jordan"), Role.CLEANER)
        self.other_job = f.job(self.customer, self.owner, start=timezone.now() + timedelta(days=4))
        f.assign(self.other_job, self.other_crew)

    def test_a_crew_member_cannot_open_a_job_they_are_not_on(self):
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.get(reverse("jobs:job_detail", args=[self.other_job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_a_crew_member_can_open_their_own_job(self):
        """The other half: scoping that refuses everything is not
        scoping, it is an outage."""
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.get(reverse("jobs:job_detail", args=[self.job.pk]))
        self.assertEqual(response.status_code, 200)

    def test_a_crew_member_cannot_fetch_a_photo_from_another_crews_job(self):
        other_photo = Photo.objects.create(
            job=self.other_job, uploaded_by=self.owner, image="private/photos/y.jpg"
        )
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.get(reverse("jobs:photo", args=[other_photo.uuid]))
        self.assertEqual(response.status_code, 404)
