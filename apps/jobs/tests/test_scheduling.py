from datetime import datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Property
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Job, JobAssignment, JobLineItem
from apps.jobs.reports import Period, summary
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"
NEW = reverse("jobs:job_create")


def local(value):
    """A datetime-local field's value, as the browser sends it."""
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


class SchedulingTestCase(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.crew = grant_role(f.user("casey", first_name="Casey"), Role.CLEANER)
        self.customer = f.contact(self.owner)
        self.service = f.service()
        self.start = f.aware(2026, 11, 3, 9)
        self.client.login(username="boss", password=PASSWORD)

    def form(self, **extra):
        data = {
            "contact": self.customer.pk,
            "primary_service_type": self.service.pk,
            "status": Job.Status.SCHEDULED,
            "scheduled_start": local(self.start),
            "scheduled_end": local(self.start + timedelta(hours=2)),
            "notes": "",
            "lines-TOTAL_FORMS": "0",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
        }
        data.update(extra)
        return data

    def with_lines(self, rows, initial=0, **extra):
        data = self.form(
            **{"lines-TOTAL_FORMS": str(len(rows)), "lines-INITIAL_FORMS": str(initial)}, **extra
        )
        for index, row in enumerate(rows):
            for key, value in row.items():
                data[f"lines-{index}-{key}"] = value
        return data


class AccessTests(SchedulingTestCase):
    def test_a_cleaner_cannot_book_or_change_a_job(self):
        job = f.job(self.customer, self.owner)
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.get(NEW).status_code, 403)
        self.assertEqual(self.client.post(NEW, self.form()).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("jobs:job_update", args=[job.pk])).status_code, 403
        )
        self.assertEqual(Job.objects.count(), 1)

    def test_a_sales_rep_can_book(self):
        grant_role(f.user("rep"), Role.SALES_REP)
        self.client.login(username="rep", password=PASSWORD)
        self.assertEqual(self.client.get(NEW).status_code, 200)

    def test_logged_out_is_sent_to_sign_in(self):
        self.client.logout()
        self.assertEqual(self.client.get(NEW).status_code, 302)

    def test_editing_a_job_out_of_scope_is_not_found(self):
        # A rep sees every job, so scope is proven with a cleaner's own
        # view of the schedule: the edit page is closed to them anyway.
        job = f.job(self.customer, self.owner)
        self.assertEqual(
            self.client.get(reverse("jobs:job_update", args=[job.pk])).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("jobs:job_update", args=[job.pk + 500])).status_code, 404
        )


class BookingTests(SchedulingTestCase):
    def test_booking_the_simplest_possible_job(self):
        response = self.client.post(NEW, self.form())
        job = Job.objects.get()
        self.assertRedirects(response, job.get_absolute_url())
        self.assertEqual(
            (job.contact, job.primary_service_type, job.created_by),
            (self.customer, self.service, self.owner),
        )
        self.assertEqual(job.scheduled_start, self.start)
        self.assertEqual(job.status, Job.Status.SCHEDULED)

    def test_the_crew_is_assigned(self):
        other = grant_role(f.user("alex"), Role.CLEANER)
        self.client.post(NEW, self.form(crew=[self.crew.pk, other.pk]))
        job = Job.objects.get()
        self.assertEqual(set(job.crew.all()), {self.crew, other})

    def test_lines_are_saved_in_order_and_priced(self):
        self.client.post(
            NEW,
            self.with_lines(
                [
                    {"service_type": self.service.pk, "quantity": "2", "unit_price": "150.00"},
                    {
                        "service_type": self.service.pk,
                        "description": "Second storey",
                        "quantity": "1",
                        "unit_price": "75.50",
                    },
                    # The blank row the page always offers, left untouched.
                    {"service_type": "", "quantity": "1", "unit_price": ""},
                ]
            ),
        )
        job = Job.objects.get()
        self.assertEqual(
            [(line.quantity, line.unit_price, line.position) for line in job.line_items.all()],
            [(Decimal("2.00"), Decimal("150.00"), 0), (Decimal("1.00"), Decimal("75.50"), 1)],
        )
        self.assertEqual(job.total, Decimal("375.50"))

    def test_an_end_before_the_start_is_refused(self):
        response = self.client.post(
            NEW, self.form(scheduled_end=local(self.start - timedelta(hours=1)))
        )
        self.assertContains(response, "after the start time")
        self.assertFalse(Job.objects.exists())

    def test_an_address_belonging_to_someone_else_is_refused(self):
        stranger = f.contact(self.owner, "Sam", "Stranger")
        theirs = Property.objects.create(
            contact=stranger, street="9 Elm St", city="Oak Park", state="IL", postal_code="60301"
        )
        response = self.client.post(NEW, self.form(service_property=theirs.pk))
        self.assertContains(response, "belongs to a different customer")
        self.assertFalse(Job.objects.exists())

    def test_the_customers_own_address_is_accepted(self):
        theirs = Property.objects.create(
            contact=self.customer,
            street="12 Oak Ave",
            city="Oak Park",
            state="IL",
            postal_code="60301",
        )
        self.client.post(NEW, self.form(service_property=theirs.pk))
        self.assertEqual(Job.objects.get().service_property, theirs)

    def test_a_day_on_the_schedule_prefills_the_morning(self):
        response = self.client.get(NEW, {"date": "2026-11-03"})
        self.assertContains(response, 'value="2026-11-03T09:00"')
        self.assertContains(response, 'value="2026-11-03T11:00"')

    def test_a_customer_can_be_prefilled_from_their_page(self):
        response = self.client.get(NEW, {"contact": str(self.customer.pk)})
        self.assertContains(response, f'<option value="{self.customer.pk}" selected>')

    def test_people_and_addresses_are_shown_by_name(self):
        Property.objects.create(
            contact=self.customer,
            street="12 Oak Ave",
            city="Oak Park",
            state="IL",
            postal_code="60301",
        )
        page = self.client.get(NEW).content.decode()
        self.assertIn("Casey", page)  # the crew member's name, not "casey"
        self.assertNotIn(">casey<", page)
        # An address says whose it is: the list holds every customer's.
        self.assertIn("Pat Homeowner — 12 Oak Ave", page)

    def test_an_inactive_service_is_not_offered(self):
        self.service.is_active = False
        self.service.save(update_fields=["is_active"])
        self.assertNotContains(self.client.get(NEW), f'value="{self.service.pk}"')

    def test_nothing_is_saved_when_a_line_is_wrong(self):
        response = self.client.post(
            NEW,
            self.with_lines(
                [{"service_type": self.service.pk, "quantity": "0", "unit_price": "10"}]
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(JobLineItem.objects.exists())


class ReschedulingTests(SchedulingTestCase):
    def setUp(self):
        super().setUp()
        self.job = f.job(self.customer, self.owner, start=self.start, lines=[])
        self.url = reverse("jobs:job_update", args=[self.job.pk])

    def test_moving_a_job(self):
        moved = self.start + timedelta(days=2)
        response = self.client.post(
            self.url,
            self.form(
                scheduled_start=local(moved), scheduled_end=local(moved + timedelta(hours=3))
            ),
        )
        self.assertRedirects(response, self.job.get_absolute_url())
        self.job.refresh_from_db()
        self.assertEqual(self.job.scheduled_start, moved)

    def test_the_form_opens_with_the_current_crew_ticked(self):
        f.assign(self.job, self.crew)
        response = self.client.get(self.url)
        self.assertEqual(
            [member.pk for member in response.context["form"]["crew"].initial], [self.crew.pk]
        )
        self.assertContains(response, "checked")

    def test_dropping_a_crew_member_keeps_the_hours_of_the_others(self):
        other = grant_role(f.user("alex"), Role.CLEANER)
        f.assign(self.job, self.crew, hours=Decimal("3.5"))
        f.assign(self.job, other, hours=Decimal("2"))
        self.client.post(self.url, self.form(crew=[self.crew.pk]))
        kept = JobAssignment.objects.get(job=self.job)
        self.assertEqual((kept.user, kept.hours_worked), (self.crew, Decimal("3.50")))

    def test_marking_a_job_finished_records_when(self):
        # Every count of finished work goes by completed_at, so a job
        # marked done without one would be counted nowhere.
        self.client.post(self.url, self.form(status=Job.Status.COMPLETED))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.COMPLETED)
        self.assertIsNotNone(self.job.completed_at)

    def test_a_finished_job_is_counted_by_the_reports(self):
        today = timezone.localdate()
        start = timezone.make_aware(datetime.combine(today, time(9)))
        self.client.post(
            self.url,
            self.form(
                status=Job.Status.COMPLETED,
                scheduled_start=local(start),
                scheduled_end=local(start + timedelta(hours=2)),
            ),
        )
        figures = summary(Period("month", today.replace(day=1), today))
        self.assertEqual(figures["jobs_completed"], 1)

    def test_reopening_a_job_clears_the_date(self):
        self.client.post(self.url, self.form(status=Job.Status.COMPLETED))
        self.client.post(self.url, self.form(status=Job.Status.IN_PROGRESS))
        self.job.refresh_from_db()
        self.assertIsNone(self.job.completed_at)

    def test_the_finish_date_is_not_moved_by_a_later_edit(self):
        self.client.post(self.url, self.form(status=Job.Status.COMPLETED))
        self.job.refresh_from_db()
        first = self.job.completed_at
        self.client.post(self.url, self.form(status=Job.Status.COMPLETED, notes="Tidied up"))
        self.job.refresh_from_db()
        self.assertEqual(self.job.completed_at, first)


class ScheduleePageTests(SchedulingTestCase):
    def test_the_new_job_button_is_only_for_sales_roles(self):
        self.assertContains(self.client.get(reverse("jobs:calendar")), "New job")
        self.client.login(username="casey", password=PASSWORD)
        self.assertNotContains(self.client.get(reverse("jobs:calendar")), "New job")

    def test_a_day_shows_one_dot_per_booking(self):
        for hour in (9, 11, 13):
            f.job(self.customer, self.owner, start=self.start.replace(hour=hour), lines=[])
        response = self.client.get(
            reverse("jobs:calendar"), {"view": "month", "date": "2026-11-03"}
        )
        day = next(d for d in response.context["days"] if d["date"].day == 3)
        self.assertEqual(len(day["indicators"]["dots"]), 3)
        self.assertEqual(day["indicators"]["jobs"], 3)
        self.assertContains(response, "day-dot")

    def test_a_very_busy_day_counts_the_rest(self):
        for hour in range(7, 16):
            f.job(self.customer, self.owner, start=self.start.replace(hour=hour), lines=[])
        response = self.client.get(
            reverse("jobs:calendar"), {"view": "month", "date": "2026-11-03"}
        )
        day = next(d for d in response.context["days"] if d["date"].day == 3)
        self.assertEqual((len(day["indicators"]["dots"]), day["indicators"]["extra"]), (6, 3))

    def test_finished_jobs_are_counted_separately(self):
        done = f.job(self.customer, self.owner, start=self.start, lines=[])
        done.status = Job.Status.COMPLETED
        done.save(update_fields=["status"])
        f.job(self.customer, self.owner, start=self.start.replace(hour=14), lines=[])
        response = self.client.get(reverse("jobs:calendar"), {"view": "day", "date": "2026-11-03"})
        self.assertEqual(response.context["days"][0]["indicators"]["done"], 1)
        self.assertContains(response, "1 finished")

    def test_an_empty_schedule_offers_to_book_one(self):
        response = self.client.get(reverse("jobs:calendar"), {"view": "day", "date": "2030-01-01"})
        self.assertContains(response, "Nothing scheduled")
        self.assertContains(response, NEW)


class CustomerListTests(SchedulingTestCase):
    """The customer picker reads in the order it is sorted.

    Contact sorts by surname but renders "Daniel Adams", so the
    dropdown looked unsorted to anyone reading the first names.
    """

    def setUp(self):
        super().setUp()
        self.client.login(username="boss", password=PASSWORD)

    def labels(self, url):
        form = self.client.get(url).context["form"]
        # Filter on the value: the empty choice's label is
        # "- Select an option -", which is truthy.
        return [str(label) for value, label in form.fields["contact"].choices if value]

    def test_booking_a_job_lists_customers_surname_first(self):
        f.contact(self.owner, first="Daniel", last="Adams")
        self.assertIn("Adams, Daniel", self.labels(NEW))

    def test_booking_a_job_lists_customers_in_alphabetical_order(self):
        for first, last in (("Brian", "Anderson"), ("Daniel", "Adams"), ("Karen", "Allen")):
            f.contact(self.owner, first=first, last=last)
        labels = self.labels(NEW)
        self.assertEqual(labels, sorted(labels))

    def test_writing_an_estimate_lists_customers_the_same_way(self):
        # Several customers, deliberately added out of order: with only
        # one, "the list is sorted" is true whatever the code does.
        for first, last in (("Brian", "Anderson"), ("Daniel", "Adams"), ("Karen", "Allen")):
            f.contact(self.owner, first=first, last=last)
        labels = self.labels(reverse("jobs:quote_create"))
        self.assertIn("Adams, Daniel", labels)
        self.assertEqual(labels, sorted(labels))
        self.assertEqual(labels[:3], ["Adams, Daniel", "Allen, Karen", "Anderson, Brian"])

    def test_two_customers_with_the_same_name_keep_a_steady_order(self):
        # Without a tiebreaker the pair can swap between page loads.
        first = f.contact(self.owner, first="John", last="Smith")
        second = f.contact(self.owner, first="John", last="Smith")
        form = self.client.get(NEW).context["form"]
        order = [c.pk for c in form.fields["contact"].queryset]
        self.assertLess(order.index(first.pk), order.index(second.pk))

    def test_a_deactivated_customer_is_not_offered_for_a_new_job(self):
        f.contact(self.owner, first="Gone", last="Away", is_active=False)
        self.assertNotIn("Away, Gone", self.labels(NEW))

    def test_a_job_whose_customer_has_left_can_still_be_edited(self):
        # Dropping them from the list would blank the field and make the
        # job unsavable.
        job = f.job(self.customer, self.owner, lines=[])
        self.customer.is_active = False
        self.customer.save(update_fields=["is_active"])
        form = self.client.get(reverse("jobs:job_update", args=[job.pk])).context["form"]
        self.assertIn(self.customer, form.fields["contact"].queryset)
