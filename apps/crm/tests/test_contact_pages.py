from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Activity, AuditLogEntry, Company, Contact, Note, Property, Tag, Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Job, Quote
from apps.jobs.tests import _factories as f
from apps.messaging.models import Channel, ChannelMembership, Message
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"


class ContactPageTestCase(TestCase):
    def setUp(self):
        self.rep = grant_role(f.user("rep"), Role.SALES_REP)
        self.client.login(username="rep", password=PASSWORD)

    def names(self, **params):
        response = self.client.get(reverse("crm:contact_list"), params)
        return [c.first_name for c in response.context["contacts"]]


class ContactListTests(ContactPageTestCase):
    def test_stage_tag_and_phone_filters(self):
        vip = Tag.objects.create(name="VIP")
        f.contact(self.rep, "Lee", "Lead", status=Contact.Status.LEAD)
        cust = f.contact(self.rep, "Cam", "Customer", phone="(585) 555-0142")
        cust.tags.add(vip)
        self.assertEqual(self.names(stage="lead"), ["Lee"])
        self.assertEqual(self.names(tag=vip.pk), ["Cam"])
        self.assertEqual(self.names(q="555-0142"), ["Cam"])
        self.assertEqual(self.names(tag="x", stage="bogus"), ["Cam", "Lee"])

    def test_last_job_and_last_contact_dates_and_sorting(self):
        recent = f.contact(self.rep, "Recent", "A")
        stale = f.contact(self.rep, "Stale", "B")
        never = f.contact(self.rep, "Never", "C")
        job = f.job(recent, self.rep, status=Job.Status.COMPLETED)
        Job.objects.filter(pk=job.pk).update(completed_at=timezone.now())
        old = Activity.objects.create(
            activity_type="call", subject="Hi", contact=stale, created_by=self.rep
        )
        Activity.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=300))
        Activity.objects.create(
            activity_type="call", subject="Hi", contact=recent, created_by=self.rep
        )

        response = self.client.get(reverse("crm:contact_list"))
        by_name = {c.first_name: c for c in response.context["contacts"]}
        self.assertIsNotNone(by_name["Recent"].last_job_at)
        self.assertIsNone(by_name["Never"].last_job_at)
        # Longest since contact first; never contacted leads the list.
        self.assertEqual(self.names(sort="last_contact"), ["Never", "Stale", "Recent"])
        self.assertEqual(self.names(sort="recent_job")[0], "Recent")
        self.assertEqual(never.pk, by_name["Never"].pk)

    def test_pagination_keeps_filters(self):
        for i in range(30):
            f.contact(self.rep, f"Lead{i:02d}", "X", status=Contact.Status.LEAD)
        response = self.client.get(reverse("crm:contact_list"), {"stage": "lead"})
        self.assertContains(response, "?stage=lead&amp;page=2")


class ContactDetailTests(ContactPageTestCase):
    def setUp(self):
        super().setUp()
        self.contact = f.contact(self.rep, "Pat", "Gutters", phone="(585) 555-0101")

    def timeline(self):
        response = self.client.get(self.contact.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        return response, response.context["timeline"]

    def test_timeline_merges_every_kind_newest_first(self):
        past = timezone.now() - timedelta(days=30)
        job = f.job(self.contact, self.rep, start=past, status=Job.Status.COMPLETED)
        Job.objects.filter(pk=job.pk).update(completed_at=past + timedelta(hours=2))
        f.quote(self.contact, self.rep, status=Quote.Status.SENT)
        Note.objects.create(author=self.rep, body="Side gate sticks", contact=self.contact)
        Activity.objects.create(
            activity_type="call",
            subject="Called about gutters",
            contact=self.contact,
            created_by=self.rep,
        )
        general = Channel.objects.get(slug="general")
        Message.objects.create(
            channel=general,
            author_user=self.rep,
            body="Pat asked for a quote",
            ref_contact=self.contact,
        )

        response, entries = self.timeline()
        self.assertEqual({e.kind for e in entries}, {"job", "quote", "note", "activity", "message"})
        self.assertEqual(entries[-1].kind, "job")  # 30 days ago: the oldest
        self.assertEqual(entries, sorted(entries, key=lambda e: e.when, reverse=True))
        self.assertContains(response, "Side gate sticks")
        self.assertContains(response, job.get_absolute_url())

    def test_direct_messages_only_show_to_members(self):
        other = grant_role(f.user("other"), Role.SALES_REP)
        dm = Channel.objects.create(
            name="Private", slug="dm-x", kind=Channel.Kind.DIRECT, created_by=other
        )
        ChannelMembership.objects.create(channel=dm, user=other)
        Message.objects.create(
            channel=dm, author_user=other, body="Secret about Pat", ref_contact=self.contact
        )

        response, entries = self.timeline()
        self.assertNotIn("message", {e.kind for e in entries})
        self.assertNotContains(response, "Secret about Pat")

        ChannelMembership.objects.create(channel=dm, user=self.rep)
        _, entries = self.timeline()
        self.assertIn("message", {e.kind for e in entries})

    def test_upcoming_jobs_properties_and_stats(self):
        Property.objects.create(
            contact=self.contact,
            label="Home",
            street="12 Elm St",
            city="Fairview",
            state="NY",
            postal_code="14625",
            is_primary=True,
            notes="Dog in yard",
        )
        future = f.job(self.contact, self.rep, start=timezone.now() + timedelta(days=3))
        f.quote(self.contact, self.rep, status=Quote.Status.DRAFT)
        response, _ = self.timeline()
        self.assertEqual(list(response.context["upcoming_jobs"]), [future])
        self.assertEqual(response.context["open_quotes"], 1)
        self.assertContains(response, "12 Elm St, Fairview, NY 14625")
        self.assertContains(response, "Dog in yard")
        self.assertContains(response, 'href="tel:(585) 555-0101"')

    def test_open_tasks_come_first(self):
        for title, status in (
            ("Old call", "completed"),
            ("Call back", "pending"),
            ("Skip", "cancelled"),
        ):
            Task.objects.create(
                title=title,
                status=status,
                contact=self.contact,
                assigned_to=self.rep,
                created_by=self.rep,
            )
        response, _ = self.timeline()
        self.assertEqual(response.context["tasks"][0].title, "Call back")

    def test_cleaners_cannot_open_contacts(self):
        grant_role(f.user("crew"), Role.CLEANER)
        self.client.login(username="crew", password=PASSWORD)
        self.assertEqual(self.client.get(self.contact.get_absolute_url()).status_code, 403)


class ContactFormTests(ContactPageTestCase):
    def post(self, contact, **extra):
        data = {"first_name": contact.first_name, "last_name": contact.last_name, "is_active": "on"}
        return self.client.post(reverse("crm:contact_update", args=[contact.pk]), {**data, **extra})

    def test_stage_source_and_tags_are_editable_and_tags_audited_by_name(self):
        contact = f.contact(self.rep, "Lee", "Lead", status=Contact.Status.LEAD)
        vip, gate = Tag.objects.create(name="VIP"), Tag.objects.create(name="Gate code")
        contact.tags.add(gate)
        self.post(contact, status="customer", lead_source="referral", tags=[vip.pk, gate.pk])
        contact.refresh_from_db()
        self.assertEqual((contact.status, contact.lead_source), ("customer", "referral"))
        entry = AuditLogEntry.objects.filter(object_id=contact.pk).latest("pk")
        self.assertEqual(entry.changes["tags"], ["Gate code", "Gate code, VIP"])

    def test_move_between_same_named_companies_is_audited(self):
        first = Company.objects.create(name="Lakeside HOA", created_by=self.rep)
        second = Company.objects.create(name="Lakeside HOA", created_by=self.rep)
        contact = f.contact(self.rep, "Pat", "Board", company=first)
        self.post(contact, company=second.pk)
        entry = AuditLogEntry.objects.filter(object_id=contact.pk).latest("pk")
        self.assertEqual(entry.changes, {"company": ["Lakeside HOA", "Lakeside HOA"]})

    def test_omitting_stage_keeps_the_current_one(self):
        contact = f.contact(self.rep, "Lee", "Lead", status=Contact.Status.LEAD)
        self.post(contact, notes="Called back")
        contact.refresh_from_db()
        self.assertEqual(contact.status, Contact.Status.LEAD)
        entry = AuditLogEntry.objects.filter(object_id=contact.pk).latest("pk")
        self.assertEqual(entry.changes, {"notes": ["", "Called back"]})
