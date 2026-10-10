"""The Owner-only change log, after Phase 18.5 unit 5 widened it.

Before this, four CRM models were recorded and the whole of the jobs,
users, core and messaging apps recorded nothing — the live database held
five rows. The page itself already existed, with undo; the work was
coverage and filters.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import AuditLogEntry, Contact, Property, Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Job
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

User = get_user_model()
PASSWORD = "correct-horse-battery"
LOG = reverse("core:activity_log")


class ChangeLogTestCase(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("riley"), Role.SALES_REP)
        self.customer = f.contact(self.owner)
        self.service = f.service()

    def as_owner(self):
        self.client.login(username="boss", password=PASSWORD)

    def entries(self, **params):
        response = self.client.get(LOG, params)
        self.assertEqual(response.status_code, 200)
        return list(response.context["entries"])


class CoverageTests(ChangeLogTestCase):
    """What now reaches the log."""

    def setUp(self):
        super().setUp()
        self.as_owner()

    def kinds_recorded(self):
        return {
            f"{e.content_type.app_label}.{e.content_type.model}"
            for e in AuditLogEntry.objects.all()
        }

    def test_booking_a_job_is_recorded(self):
        start = timezone.now() + timedelta(days=1)
        self.client.post(
            reverse("jobs:job_create"),
            {
                "contact": self.customer.pk,
                "primary_service_type": self.service.pk,
                "status": Job.Status.SCHEDULED,
                "scheduled_start": timezone.localtime(start).strftime("%Y-%m-%dT%H:%M"),
                "scheduled_end": timezone.localtime(start + timedelta(hours=2)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "sales_rep": self.owner.pk,
                "notes": "",
                "lines-TOTAL_FORMS": "0",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertIn("jobs.job", self.kinds_recorded())

    def test_moving_a_job_records_only_what_changed(self):
        job = f.job(self.customer, self.owner, lines=[])
        AuditLogEntry.objects.all().delete()
        self.client.post(
            reverse("jobs:job_status", args=[job.pk]), {"status": Job.Status.IN_PROGRESS}
        )
        entry = AuditLogEntry.objects.get()
        self.assertEqual(list(entry.changes), ["status"])
        self.assertEqual(entry.changes["status"][1], "In progress")

    def test_marking_a_job_complete_from_the_schedule_is_recorded(self):
        job = f.job(self.customer, self.owner, lines=[])
        AuditLogEntry.objects.all().delete()
        self.client.post(
            reverse("jobs:job_status", args=[job.pk]), {"status": Job.Status.COMPLETED}
        )
        self.assertEqual(AuditLogEntry.objects.count(), 1)

    def test_a_rejected_job_records_nothing_and_does_not_crash(self):
        """A valid form is not a completed save.

        The job views validate a line-item formset inside their own
        `form_valid` and re-render when a line is wrong, leaving
        `self.object` unset. The first version of the mixin recorded
        regardless: it logged a creation that never happened, and threw
        `AttributeError: 'NoneType' object has no attribute '_meta'` on
        the way out — a 500 on an ordinary typo in a price.
        """
        start = timezone.now() + timedelta(days=1)
        response = self.client.post(
            reverse("jobs:job_create"),
            {
                "contact": self.customer.pk,
                "primary_service_type": self.service.pk,
                "status": Job.Status.SCHEDULED,
                "scheduled_start": timezone.localtime(start).strftime("%Y-%m-%dT%H:%M"),
                "scheduled_end": timezone.localtime(start + timedelta(hours=2)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "sales_rep": self.owner.pk,
                "notes": "",
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-service_type": self.service.pk,
                "lines-0-description": "",
                "lines-0-quantity": "not a number",
                "lines-0-unit_price": "100",
            },
        )
        self.assertEqual(response.status_code, 200)  # redisplayed, not saved
        self.assertEqual(Job.objects.count(), 0)
        self.assertEqual(AuditLogEntry.objects.count(), 0)

    def test_adding_an_address_is_recorded(self):
        self.client.post(
            reverse("crm:property_create"),
            {
                "contact": self.customer.pk,
                "label": "Home",
                "street": "1 Any St",
                "city": "Penfield",
                "state": "NY",
                "postal_code": "14526",
                "notes": "",
            },
        )
        self.assertIn("crm.property", self.kinds_recorded())

    def test_a_task_edit_is_recorded(self):
        task = Task.objects.create(title="Ring them", assigned_to=self.owner, created_by=self.owner)
        AuditLogEntry.objects.all().delete()
        self.client.post(
            reverse("crm:task_update", args=[task.pk]),
            {
                "title": "Ring them twice",
                "assigned_to": self.owner.pk,
                "priority": Task.Priority.MEDIUM,
                "status": Task.Status.PENDING,
            },
        )
        entry = AuditLogEntry.objects.get()
        self.assertEqual(entry.changes["title"], ["Ring them", "Ring them twice"])

    def test_completing_a_task_in_one_click_is_recorded(self):
        task = Task.objects.create(title="Do it", assigned_to=self.owner, created_by=self.owner)
        AuditLogEntry.objects.all().delete()
        self.client.post(reverse("crm:task_complete", args=[task.pk]))
        entry = AuditLogEntry.objects.get()
        self.assertEqual(entry.changes["status"][1], "Completed")

    def test_an_edit_that_changes_nothing_records_nothing(self):
        """A log of everything is only readable if it holds changes."""
        task = Task.objects.create(title="Same", assigned_to=self.owner, created_by=self.owner)
        AuditLogEntry.objects.all().delete()
        self.client.post(
            reverse("crm:task_update", args=[task.pk]),
            {
                "title": "Same",
                "assigned_to": self.owner.pk,
                "priority": Task.Priority.MEDIUM,
                "status": Task.Status.PENDING,
            },
        )
        self.assertEqual(AuditLogEntry.objects.count(), 0)

    def test_the_log_says_who_made_the_change(self):
        task = Task.objects.create(title="Mine", assigned_to=self.owner, created_by=self.owner)
        AuditLogEntry.objects.all().delete()
        self.client.post(reverse("crm:task_complete", args=[task.pk]))
        self.assertEqual(AuditLogEntry.objects.get().user_id, self.owner.pk)

    def test_placing_a_pin_is_not_recorded(self):
        """Machine-written coordinates would flood a log nobody reads."""
        address = Property.objects.create(
            contact=self.customer,
            street="1 Any St",
            city="Penfield",
            state="NY",
            postal_code="14526",
        )
        AuditLogEntry.objects.all().delete()
        self.client.post(
            reverse("jobs:property_locate", args=[address.pk]),
            {"lat": "43.1", "lng": "-77.6"},
        )
        self.assertEqual(AuditLogEntry.objects.count(), 0)

    def test_the_existing_customer_entries_still_work(self):
        """Regression for lifting the helpers out of crm/views.py."""
        AuditLogEntry.objects.all().delete()
        self.client.post(
            reverse("crm:contact_update", args=[self.customer.pk]),
            {
                "first_name": "Renamed",
                "last_name": self.customer.last_name,
                "status": Contact.Status.CUSTOMER,
                "is_active": "on",
            },
        )
        entry = AuditLogEntry.objects.get()
        self.assertEqual(entry.changes["first_name"][1], "Renamed")


class UndoScopeTests(ChangeLogTestCase):
    """Undo must not follow the log's coverage.

    `undo.RESTORABLE` includes CharField, so without an explicit
    allow-list `Job.status` became undoable the moment jobs reached the
    log — and undoing it writes the status while leaving `completed_at`
    alone, which is the silent reporting loss apps/jobs/status.py exists
    to prevent.
    """

    def setUp(self):
        super().setUp()
        self.as_owner()

    def test_a_job_change_cannot_be_undone_from_the_log(self):
        job = f.job(self.customer, self.owner, lines=[])
        self.client.post(
            reverse("jobs:job_status", args=[job.pk]), {"status": Job.Status.COMPLETED}
        )
        entry = AuditLogEntry.objects.filter(content_type__model="job").get()
        response = self.client.post(reverse("core:activity_undo", args=[entry.pk]), follow=True)
        self.assertEqual(response.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.COMPLETED)
        self.assertIsNotNone(job.completed_at)

    def test_the_page_says_why_a_job_change_cannot_be_undone(self):
        job = f.job(self.customer, self.owner, lines=[])
        self.client.post(
            reverse("jobs:job_status", args=[job.pk]), {"status": Job.Status.COMPLETED}
        )
        rows = self.client.get(LOG).context["rows"]
        blocked = [r["blocked"] for r in rows if r["entry"].content_type.model == "job"]
        self.assertTrue(all(blocked), blocked)
        self.assertIn("can't be put back", blocked[0])

    def test_a_task_change_cannot_be_undone_either(self):
        task = Task.objects.create(title="Do it", assigned_to=self.owner, created_by=self.owner)
        self.client.post(reverse("crm:task_complete", args=[task.pk]))
        entry = AuditLogEntry.objects.filter(content_type__model="task").get()
        self.client.post(reverse("core:activity_undo", args=[entry.pk]))
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.COMPLETED)

    def test_a_customer_change_can_still_be_undone(self):
        """The four models undo has always handled keep working."""
        self.client.post(
            reverse("crm:contact_update", args=[self.customer.pk]),
            {
                "first_name": "Renamed",
                "last_name": self.customer.last_name,
                "status": Contact.Status.CUSTOMER,
                "is_active": "on",
            },
        )
        entry = AuditLogEntry.objects.filter(content_type__model="contact").latest("pk")
        self.client.post(reverse("core:activity_undo", args=[entry.pk]))
        self.customer.refresh_from_db()
        self.assertNotEqual(self.customer.first_name, "Renamed")


class FilterTests(ChangeLogTestCase):
    def setUp(self):
        super().setUp()
        self.job = f.job(self.customer, self.owner, lines=[])
        self.as_owner()
        self.client.post(
            reverse("jobs:job_status", args=[self.job.pk]), {"status": Job.Status.IN_PROGRESS}
        )
        self.client.post(
            reverse("crm:contact_update", args=[self.customer.pk]),
            {
                "first_name": "Renamed",
                "last_name": self.customer.last_name,
                "status": Contact.Status.CUSTOMER,
                "is_active": "on",
            },
        )

    def test_without_filters_everything_is_listed(self):
        self.assertEqual(len(self.entries()), 2)

    def test_it_can_be_narrowed_to_one_kind_of_record(self):
        shown = self.entries(what="jobs.job")
        self.assertEqual([e.content_type.model for e in shown], ["job"])

    def test_it_can_be_narrowed_to_one_person(self):
        self.assertEqual(len(self.entries(who=str(self.owner.pk))), 2)
        self.assertEqual(len(self.entries(who=str(self.rep.pk))), 0)

    def test_it_can_be_narrowed_to_created_or_changed(self):
        self.assertEqual(len(self.entries(action=AuditLogEntry.Action.CREATED)), 0)
        self.assertEqual(len(self.entries(action=AuditLogEntry.Action.UPDATED)), 2)

    def test_it_can_be_narrowed_to_a_date_range(self):
        today = timezone.localdate()
        self.assertEqual(len(self.entries(**{"from": str(today), "to": str(today)})), 2)
        tomorrow = today + timedelta(days=1)
        self.assertEqual(len(self.entries(**{"from": str(tomorrow)})), 0)
        self.assertEqual(len(self.entries(to=str(today - timedelta(days=1)))), 0)

    def test_the_filters_combine(self):
        self.assertEqual(len(self.entries(who=str(self.owner.pk), what="jobs.job")), 1)

    def test_an_unknown_kind_is_ignored_rather_than_an_error(self):
        self.assertEqual(len(self.entries(what="not.athing")), 0)
        self.assertEqual(len(self.entries(what="nonsense")), 2)

    def test_nonsense_values_are_ignored_rather_than_an_error(self):
        self.assertEqual(len(self.entries(who="banana")), 2)
        self.assertEqual(len(self.entries(action="banana")), 2)
        self.assertEqual(len(self.entries(**{"from": "not-a-date"})), 2)

    def test_the_choices_offer_only_what_has_been_recorded(self):
        response = self.client.get(LOG)
        kinds = dict(response.context["kinds"])
        self.assertEqual(set(kinds), {"jobs.job", "crm.contact"})
        self.assertEqual([p.pk for p in response.context["people"]], [self.owner.pk])

    def test_the_filters_are_kept_when_paging(self):
        response = self.client.get(LOG, {"what": "jobs.job"})
        self.assertContains(response, 'value="jobs.job" selected')

    def test_the_newest_change_is_first(self):
        shown = self.entries()
        self.assertGreaterEqual(shown[0].created_at, shown[-1].created_at)

    def test_the_page_says_it_only_covers_changes_made_in_the_app(self):
        self.assertContains(self.client.get(LOG), "Django admin")


class AccessTests(ChangeLogTestCase):
    def test_the_owner_can_open_it(self):
        self.as_owner()
        self.assertEqual(self.client.get(LOG).status_code, 200)

    def test_a_superuser_outside_the_owner_group_can_open_it(self):
        User.objects.create_superuser("root", password=PASSWORD, email="")
        self.client.login(username="root", password=PASSWORD)
        self.assertEqual(self.client.get(LOG).status_code, 200)

    def test_a_sales_rep_is_refused(self):
        self.client.login(username="riley", password=PASSWORD)
        self.assertEqual(self.client.get(LOG).status_code, 403)

    def test_a_crew_member_is_refused(self):
        grant_role(f.user("casey"), Role.CLEANER)
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.get(LOG).status_code, 403)

    def test_a_signed_out_visitor_is_sent_to_sign_in(self):
        self.assertEqual(self.client.get(LOG).status_code, 302)


class QueryCountTests(ChangeLogTestCase):
    def test_the_page_does_not_ask_a_question_per_row(self):
        """A generic relation makes this the easy mistake.

        Compares two sizes rather than pinning a measured number: a
        hardcoded count taken from a run of the code passes whatever
        that code does.
        """
        self.as_owner()

        def queries_for(count):
            AuditLogEntry.objects.all().delete()
            for i in range(count):
                task = Task.objects.create(
                    title=f"T{i}", assigned_to=self.owner, created_by=self.owner
                )
                self.client.post(reverse("crm:task_complete", args=[task.pk]))
            AuditLogEntry.objects.exclude(content_type__model="task").delete()
            with CaptureQueriesContext(connection) as captured:
                self.client.get(LOG)
            return len(captured.captured_queries)

        few, many = queries_for(2), queries_for(14)
        self.assertEqual(few, many, f"{few} queries for 2 rows, {many} for 14")


class MixinPlacementTests(TestCase):
    """`AuditedFormMixin` has to be somewhere the MRO reaches it.

    A class's own `form_valid` beats one it inherits, so declaring the
    mixin among the bases of a class that defines `form_valid` itself
    does nothing unless that method calls `super().form_valid()`. That
    is how it was first wired here: the job saved, the page redirected,
    and nothing was recorded.

    This walks every view that declares the mixin and checks the
    placement structurally, so the next view added cannot repeat it.
    """

    def views_using_the_mixin(self):
        import inspect

        from apps.crm import views as crm_views
        from apps.crm.audit import AuditedFormMixin
        from apps.jobs import views as jobs_views

        found = []
        for module in (crm_views, jobs_views):
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    obj is not AuditedFormMixin
                    and issubclass(obj, AuditedFormMixin)
                    and hasattr(obj, "as_view")  # a view, not another mixin
                ):
                    found.append(obj)
        return found

    def test_there_are_views_to_check(self):
        self.assertGreater(len(self.views_using_the_mixin()), 8)

    def test_the_audit_mixin_is_actually_reachable(self):
        import inspect

        from apps.crm.audit import AuditedFormMixin

        broken = []
        for view in self.views_using_the_mixin():
            for klass in view.__mro__:
                if klass is AuditedFormMixin:
                    break  # reached it before anything shadowed it
                if "form_valid" in vars(klass):
                    source = inspect.getsource(vars(klass)["form_valid"])
                    if "super().form_valid" not in source:
                        broken.append(f"{view.__name__}: {klass.__name__}.form_valid")
                    break
        self.assertEqual(broken, [], "these shadow the mixin without calling super()")
