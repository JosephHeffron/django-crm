import os
from datetime import datetime, timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.management.commands.seed_demo import DEMO_PREFIX, DEMO_USERS, TOWNS
from apps.core.models import Goal, Notification
from apps.crm.models import Contact, Property, Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Invoice, Job, Quote, ServiceType, TimeEntry
from apps.messaging.models import Channel, ChannelMembership, Message
from apps.messaging.services import direct_channel
from apps.users.models import UserProfile
from apps.users.roles import Role, user_role

User = get_user_model()
ENV = {"DEMO_USER_PASSWORD": "demo-pass-for-tests"}


def seed(*args):
    out = StringIO()
    with mock.patch.dict(os.environ, ENV):
        call_command("seed_demo", *args, stdout=out)
    return out.getvalue()


@override_settings(DEBUG=True)
class SeedDemoTests(TestCase):
    def setUp(self):
        # Pre-existing, non-demo data that seeding and resetting must not touch.
        self.real_user = grant_role(User.objects.create_user("realowner", password="x"), Role.OWNER)
        self.real_contact = Contact.objects.create(
            first_name="My", last_name="Customer", created_by=self.real_user
        )

    def test_populates_every_area_with_real_data(self):
        out = seed()
        self.assertIn("Demo data created:", out)
        self.assertNotIn("Demo password", out)  # chosen via env, not printed

        demo = {
            u.username: user_role(u) for u in User.objects.filter(username__startswith=DEMO_PREFIX)
        }
        self.assertEqual(len(demo), len(DEMO_USERS))
        self.assertEqual(demo["demo_owner"], Role.OWNER)
        self.assertEqual(demo["demo_casey"], Role.CLEANER)

        self.assertEqual(Contact.objects.exclude(pk=self.real_contact.pk).count(), 60)
        self.assertTrue(Contact.objects.filter(status=Contact.Status.LEAD).exists())
        statuses = set(Quote.objects.values_list("status", flat=True))
        self.assertEqual(statuses, set(Quote.Status.values))
        self.assertTrue(Job.objects.filter(status=Job.Status.COMPLETED).exists())
        self.assertTrue(Job.objects.filter(status=Job.Status.SCHEDULED).exists())
        self.assertTrue(Invoice.objects.exists())
        self.assertTrue(Task.objects.filter(kind=Task.Kind.FOLLOW_UP).exists())
        # The dashboard's bell and goals card have something real to show.
        self.assertTrue(Notification.objects.filter(kind=Notification.Kind.TASK).exists())
        self.assertTrue(Notification.objects.filter(kind=Notification.Kind.FOLLOW_UP).exists())
        self.assertEqual(
            set(Goal.objects.values_list("metric", flat=True)), set(Goal.Metric.values)
        )
        self.assertTrue(all(target > 0 for target in Goal.objects.values_list("target", flat=True)))
        # Crew have a rate and clocked time, so Payroll isn't an empty page.
        self.assertTrue(TimeEntry.objects.filter(ended_at__isnull=False).exists())
        # Most addresses are placed locally, so the Map has pins without
        # anything being sent to OpenStreetMap during a seed.
        placed = Property.objects.filter(latitude__isnull=False).count()
        unplaced = Property.objects.filter(latitude__isnull=True).count()
        self.assertGreater(placed, unplaced)
        # And a few are deliberately left, so the Map's "Still to place"
        # list, its "Look it up" button and the pin-drop form all have
        # something to show. Every address used to be pre-placed, which
        # left that half of the page looking broken.
        self.assertGreater(unplaced, 0)
        rates = UserProfile.objects.filter(
            user__username__startswith=DEMO_PREFIX, hourly_rate__isnull=False
        )
        self.assertTrue(rates.exists())
        self.assertTrue(all(profile.working_days for profile in rates))
        self.assertEqual(Message.objects.filter(channel__slug="crew").count(), 12)
        self.assertEqual(Channel.objects.filter(kind=Channel.Kind.DIRECT).count(), 2)
        # Opening a seeded DM in the app finds it rather than starting another.
        direct_channel(
            User.objects.get(username="demo_casey"), User.objects.get(username="demo_jordan")
        )
        self.assertEqual(Channel.objects.filter(kind=Channel.Kind.DIRECT).count(), 2)
        # Posting order and timestamps agree.
        times = list(
            Message.objects.filter(channel__slug="crew")
            .order_by("pk")
            .values_list("created_at", flat=True)
        )
        self.assertEqual(times, sorted(times))
        # #sales is sales-only, so no cleaner is a member.
        self.assertFalse(
            ChannelMembership.objects.filter(
                channel__slug="sales", user__username="demo_casey"
            ).exists()
        )
        # A message that names a customer links to them (contact timeline).
        for message in Message.objects.filter(channel__slug="sales", ref_contact__isnull=True):
            self.assertFalse(
                any(str(c) in message.body for c in Contact.objects.all()), message.body
            )
        # Real accounts can read the demo chat…
        self.assertTrue(ChannelMembership.objects.filter(user=self.real_user).exists())

    def test_never_modifies_real_records(self):
        seed()
        self.real_contact.refresh_from_db()
        self.assertEqual(self.real_contact.first_name, "My")
        self.assertFalse(Task.objects.filter(contact=self.real_contact).exists())

    def test_refuses_to_run_twice_without_reset(self):
        seed()
        with self.assertRaises(CommandError):
            seed()

    def test_reset_replaces_demo_data_and_keeps_real_and_reference_data(self):
        seed()
        first_jobs = Job.objects.count()
        services = ServiceType.objects.count()

        out = seed("--reset")

        self.assertIn(f"Removed existing demo data ({len(DEMO_USERS)} demo users)", out)
        self.assertEqual(Job.objects.count(), first_jobs)  # same seed → same data
        self.assertEqual(
            User.objects.filter(username__startswith=DEMO_PREFIX).count(), len(DEMO_USERS)
        )
        self.assertTrue(Contact.objects.filter(pk=self.real_contact.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.real_user.pk).exists())
        self.assertEqual(ServiceType.objects.count(), services)
        # Goals belong to nobody, so --reset has to clear them itself
        # rather than relying on the demo users going away.
        self.assertEqual(Goal.objects.count(), len(Goal.Metric.values))
        self.assertEqual(
            set(Channel.objects.filter(kind=Channel.Kind.PUBLIC).values_list("slug", flat=True)),
            {"general", "crew", "sales"},
        )

    def test_generates_a_password_when_none_is_given(self):
        out = StringIO()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEMO_USER_PASSWORD", None)
            call_command("seed_demo", stdout=out)
        self.assertIn("Demo password (shown once", out.getvalue())


class SeedDemoGuardTests(TestCase):
    @override_settings(DEBUG=False)
    def test_refuses_without_debug(self):
        with self.assertRaises(CommandError):
            seed()
        self.assertFalse(User.objects.filter(username__startswith=DEMO_PREFIX).exists())


class SeededAddressTests(TestCase):
    """The addresses have to be ones OpenStreetMap can actually find.

    They used to be invented streets in invented towns, so every
    lookup failed and the Map page looked broken. They are real roads
    in real towns now, with made-up house numbers — public
    thoroughfares, not dwellings, so no seeded row says where a real
    household lives.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--force", verbosity=0)

    def test_every_town_and_postcode_pairing_is_one_the_seed_knows(self):
        known = {(town, postal) for town, postal, *_ in TOWNS}
        actual = set(Property.objects.values_list("city", "postal_code"))
        self.assertTrue(actual)
        self.assertEqual(actual - known, set())

    def test_every_street_belongs_to_the_town_it_is_in(self):
        """A real road in the wrong town would not geocode either."""
        roads_by_town = {}
        for town, postal, _, _, roads in TOWNS:
            roads_by_town.setdefault((town, postal), set()).update(roads)
        wrong = [
            str(p)
            for p in Property.objects.all()
            if not any(
                p.street.endswith(road) for road in roads_by_town.get((p.city, p.postal_code), ())
            )
        ]
        self.assertEqual(wrong, [])

    def test_a_placed_address_sits_near_its_own_town(self):
        centres = {(town, postal): (lat, lng) for town, postal, lat, lng, _ in TOWNS}
        far = []
        for p in Property.objects.filter(latitude__isnull=False):
            lat, lng = centres[(p.city, p.postal_code)]
            if abs(float(p.latitude) - lat) > 0.05 or abs(float(p.longitude) - lng) > 0.05:
                far.append(str(p))
        self.assertEqual(far, [])

    def test_seeding_never_asks_openstreetmap_anything(self):
        """The most important one here.

        Seeding has to work with no network: tests run offline, and
        Nominatim allows one request a second, so a seed that looked up
        sixty addresses would take a minute and hammer a free service.
        """
        with mock.patch("apps.crm.geocoding.lookup") as lookup:
            with mock.patch("apps.crm.geocoding.urlopen") as opener:
                call_command("seed_demo", "--force", "--reset", verbosity=0)
        lookup.assert_not_called()
        opener.assert_not_called()

    def test_the_crew_have_clocked_time_whatever_the_hour(self):
        """Payroll must not seed empty depending on the clock.

        Time entries come from jobs completed in the last fortnight,
        and the only recent completions used to be today's — seeded at
        8am, 11am and 2pm with their status read from the clock. Before
        the first ended there was nothing in the window, so Payroll came
        up empty, which is how `test_populates_every_area_with_real_data`
        failed one Saturday morning and passed the same afternoon.
        """
        self.assertTrue(TimeEntry.objects.filter(ended_at__isnull=False).exists())
        self.assertFalse(
            TimeEntry.objects.filter(job__isnull=True).exists(),
            "clocked time should name the job it was worked on",
        )

    def test_payroll_has_hours_even_seeded_before_dawn(self):
        """The test the first attempt could not have had.

        Everything else here runs at whatever hour CI happens to run,
        so none of it can fail while today's 8am job has already
        finished — which is why two mutation checks of the broken
        behaviour passed at ten in the morning and proved nothing.

        So the clock is pinned to a Wednesday at 6am, before any of
        today's jobs could have ended, and the seed is asked for data
        again. That is the state in which Payroll used to come up
        empty.
        """
        from apps.jobs import crew

        dawn = timezone.make_aware(datetime(2026, 10, 7, 6, 0))  # a Wednesday
        with mock.patch.object(timezone, "localtime", return_value=dawn):
            with mock.patch.object(timezone, "now", return_value=dawn):
                call_command("seed_demo", "--force", "--reset", verbosity=0)

        first, last = crew.week_bounds(dawn.date())
        hours = TimeEntry.objects.filter(started_at__date__gte=first, started_at__date__lte=last)
        self.assertTrue(
            hours.exists(),
            "seeded at 6am, Payroll's own week has no clocked hours in it",
        )
        rows = crew.payroll(list(crew.payroll_people()), first, last)
        self.assertTrue(
            any(row["hours"] for row in rows),
            "Payroll reports no hours for the week it is showing",
        )

    def test_the_clocked_hours_land_where_payroll_looks(self):
        """The assertion the first attempt was missing.

        A row existing somewhere is not the promise. Payroll reports a
        period, so hours dated to a job from two months ago leave it
        exactly as empty — which is what a fallback to "the most
        recently finished jobs whenever they were" would have produced.
        """
        from apps.jobs import crew

        first, last = crew.week_bounds(timezone.localdate())
        entries = TimeEntry.objects.filter(
            started_at__date__gte=first - timedelta(days=7), started_at__date__lte=last
        )
        self.assertTrue(
            entries.exists(),
            "no clocked time within the week Payroll shows, or the one before it",
        )
        rows = crew.payroll(list(crew.payroll_people()), first - timedelta(days=7), last)
        self.assertTrue(
            any(row["hours"] for row in rows),
            "Payroll reports no hours for a period the seed claims to fill",
        )

    def test_clocked_time_is_only_ever_for_demo_people(self):
        """The seed must never write against a real person's payroll.

        `remove_demo_data()` cleans up demo users only, so an entry
        against anyone else would survive a reset.
        """
        outsiders = [
            entry.user.username
            for entry in TimeEntry.objects.select_related("user")
            if not entry.user.username.startswith(DEMO_PREFIX)
        ]
        self.assertEqual(outsiders, [])

    def test_no_clocked_time_comes_from_an_undated_job(self):
        # A NULL completed_at sorts first on PostgreSQL, so an undated
        # job could otherwise be picked as recent work.
        self.assertFalse(TimeEntry.objects.filter(job__completed_at__isnull=True).exists())

    def test_clocked_time_belongs_to_somebody_assigned_to_the_job(self):
        wrong = [
            entry.pk
            for entry in TimeEntry.objects.select_related("job").all()
            if not entry.job.assignments.filter(user=entry.user).exists()
        ]
        self.assertEqual(wrong, [])

    def test_the_house_numbers_are_not_all_the_same(self):
        # A fixed number would make every address on a road identical.
        numbers = {p.street.split(" ", 1)[0] for p in Property.objects.all()}
        self.assertGreater(len(numbers), 5)
