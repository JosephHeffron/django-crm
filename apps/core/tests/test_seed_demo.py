import os
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.core.management.commands.seed_demo import DEMO_PREFIX, DEMO_USERS
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
        # Addresses are placed locally, so the Map has pins and no
        # made-up address is ever sent to OpenStreetMap.
        self.assertFalse(Property.objects.filter(latitude__isnull=True).exists())
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
