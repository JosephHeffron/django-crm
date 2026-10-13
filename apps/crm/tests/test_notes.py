"""Writing notes — in the hub, and at the kerb.

Phase 19 unit 3. `NoteListView`'s docstring said "Adding and editing
notes lands in Phase 19" and the Django admin was the only way to write
one.

Two audiences, deliberately different:

- **Sales and the owner**, from the Tasks hub: a general note, or one
  about a customer or a job.
- **A crew member**, from the page of a job they are on. `users/0004`
  has granted crews `add_note` since Phase 17 — "Crews update their own
  jobs (status, hours) and add photos/notes — which jobs is enforced
  row-by-row in the views" — and the view that enforces it was never
  built, so the permission sat there unreachable.

The owner chose that a crew member on a job sees notes about the
**customer** as well as about the job. That is the more useful view at
the house and the less private one, so the trade is asserted in both
directions below: the crew member can read the customer's notes, and
cannot edit any note or reach the notes list.
"""

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import AuditLogEntry, Note
from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"


class HubNoteTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.customer = f.contact(self.owner)
        self.job = f.job(self.customer, self.owner)
        self.client.login(username="boss", password=PASSWORD)

    def post_note(self, **extra):
        data = {"body": "Van needs a service", "contact": "", "job": "", "pinned": ""}
        data.update(extra)
        return self.client.post(reverse("crm:note_create"), data)

    def test_a_general_note_can_be_written(self):
        """The gap this unit closes: the admin was the only way in."""
        response = self.post_note()
        self.assertIn(response.status_code, (301, 302))
        note = Note.objects.get()
        self.assertEqual(note.body, "Van needs a service")
        self.assertEqual(note.author, self.owner)
        self.assertIsNone(note.contact)
        self.assertIsNone(note.job)

    def test_a_note_can_be_about_a_customer(self):
        self.post_note(contact=self.customer.pk)
        self.assertEqual(Note.objects.get().contact, self.customer)

    def test_a_note_can_be_about_a_job(self):
        self.post_note(contact=self.customer.pk, job=self.job.pk)
        note = Note.objects.get()
        self.assertEqual((note.contact, note.job), (self.customer, self.job))

    def test_a_note_cannot_name_a_customer_and_someone_elses_job(self):
        """Two fields that must agree are two fields that can disagree.
        It would show up in both places, each time beside the wrong
        person — the same guard TaskForm and JobForm already apply."""
        other = f.contact(self.owner, "Someone", "Else")
        other_job = f.job(other, self.owner, start=timezone.now() + timedelta(days=5))
        response = self.post_note(contact=self.customer.pk, job=other_job.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("job", response.context["form"].errors)
        self.assertFalse(Note.objects.exists())

    def test_an_empty_note_is_refused(self):
        response = self.post_note(body="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("body", response.context["form"].errors)
        self.assertFalse(Note.objects.exists())

    def test_the_form_warns_that_customer_notes_are_read_in_the_field(self):
        """The owner chose to show customer notes to crews on their
        jobs. Somebody writing one has no way to know that unless the
        form says so, so this asserts it does — the mitigation is the
        point, not decoration.
        """
        response = self.client.get(reverse("crm:note_create"))
        help_text = str(response.context["form"].fields["contact"].help_text)
        self.assertIn("crew", help_text.lower())
        self.assertContains(response, "commercial detail")
        # The reach has to be stated accurately, which the first
        # version of this warning did not: it said "this customer's
        # address", while `JobDetailView` filters notes by **contact**.
        # A customer with three addresses has their notes readable by a
        # crew member on any one of those jobs. A warning that
        # understates itself is worse than none.
        self.assertIn("jobs", help_text.lower())
        self.assertNotIn("this customer's address", help_text)

    def test_a_note_can_be_edited(self):
        note = Note.objects.create(body="Typo", author=self.owner)
        response = self.client.post(
            reverse("crm:note_update", args=[note.pk]),
            {"body": "Fixed", "contact": "", "job": "", "pinned": "on"},
        )
        self.assertIn(response.status_code, (301, 302))
        note.refresh_from_db()
        self.assertEqual(note.body, "Fixed")
        self.assertTrue(note.pinned)

    def test_the_list_offers_a_way_in_and_out(self):
        note = Note.objects.create(body="Something", author=self.owner)
        response = self.client.get(reverse("crm:note_list"))
        self.assertContains(response, reverse("crm:note_create"))
        self.assertContains(response, reverse("crm:note_update", args=[note.pk]))

    def test_editing_returns_to_the_filtered_list_it_came_from(self):
        note = Note.objects.create(body="Something", author=self.owner)
        back = f"{reverse('crm:note_list')}?about=general"
        response = self.client.post(
            f"{reverse('crm:note_update', args=[note.pk])}?next={back}",
            {"body": "Changed", "contact": "", "job": "", "pinned": ""},
        )
        self.assertRedirects(response, back)

    def test_a_next_pointing_off_this_site_is_ignored(self):
        note = Note.objects.create(body="Something", author=self.owner)
        response = self.client.post(
            f"{reverse('crm:note_update', args=[note.pk])}?next=https://evil.test/go",
            {"body": "Changed", "contact": "", "job": "", "pinned": ""},
        )
        self.assertRedirects(response, reverse("crm:note_list"))

    def test_writing_a_note_is_recorded_in_the_change_log(self):
        self.post_note()
        note = Note.objects.get()
        entry = AuditLogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Note), object_id=note.pk
        ).latest("pk")
        self.assertEqual(entry.action, "created")

    def test_a_logged_note_links_somewhere_real(self):
        """The change log renders `record.get_absolute_url` for every
        entry, and Django resolves a missing attribute to the empty
        string **silently** — so without one this is a link that goes
        nowhere, invisible until clicked.
        """
        general = Note.objects.create(body="General", author=self.owner)
        self.assertEqual(general.get_absolute_url(), reverse("crm:note_list"))
        about_customer = Note.objects.create(
            body="About them", author=self.owner, contact=self.customer
        )
        self.assertEqual(about_customer.get_absolute_url(), self.customer.get_absolute_url())
        about_job = Note.objects.create(body="About it", author=self.owner, job=self.job)
        self.assertEqual(about_job.get_absolute_url(), self.job.get_absolute_url())

    def test_the_change_log_page_renders_with_a_note_in_it(self):
        self.post_note(contact=self.customer.pk)
        response = self.client.get(reverse("core:activity_log"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.customer.get_absolute_url())


class JobNoteTests(TestCase):
    """A note written at the kerb, on a phone."""

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("riley"), Role.SALES_REP)
        self.casey = grant_role(f.user("casey"), Role.CLEANER)
        self.jordan = grant_role(f.user("jordan"), Role.CLEANER)
        self.customer = f.contact(self.owner)
        self.job = f.job(self.customer, self.owner)
        f.assign(self.job, self.casey)
        self.other_job = f.job(self.customer, self.owner, start=timezone.now() + timedelta(days=6))
        f.assign(self.other_job, self.jordan)
        self.url = reverse("jobs:job_note_create", args=[self.job.pk])

    def test_a_crew_member_can_note_a_job_they_are_on(self):
        """The permission `users/0004` granted in Phase 17 and nothing
        had ever made reachable."""
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.post(self.url, {"body": "Gate code 4821, side entrance"})
        self.assertRedirects(response, self.job.get_absolute_url())
        note = Note.objects.get()
        self.assertEqual(note.body, "Gate code 4821, side entrance")
        self.assertEqual(note.author, self.casey)
        self.assertEqual(note.job, self.job)

    def test_the_note_is_attached_to_the_job_not_the_customer(self):
        """A crew member's note about today's work is not a note on the
        customer's permanent record."""
        self.client.login(username="casey", password=PASSWORD)
        self.client.post(self.url, {"body": "Dog in the back garden"})
        self.assertIsNone(Note.objects.get().contact)

    def test_a_crew_member_cannot_note_a_job_they_are_not_on(self):
        """404, never 403 — a 403 confirms the job exists."""
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.post(
            reverse("jobs:job_note_create", args=[self.other_job.pk]), {"body": "Nope"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Note.objects.exists())

    def test_an_empty_note_is_refused_with_a_message(self):
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.post(self.url, {"body": ""}, follow=True)
        self.assertFalse(Note.objects.exists())
        said = " ".join(str(m) for m in response.context["messages"])
        self.assertTrue(said, "an empty note was rejected silently")

    def test_the_job_page_offers_the_form_to_a_crew_member(self):
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.get(self.job.get_absolute_url())
        self.assertContains(response, self.url)

    def test_a_get_writes_nothing(self):
        self.client.login(username="casey", password=PASSWORD)
        self.assertIn(self.client.get(self.url).status_code, (403, 405))
        self.assertFalse(Note.objects.exists())

    def test_the_note_is_recorded_in_the_change_log(self):
        self.client.login(username="casey", password=PASSWORD)
        self.client.post(self.url, {"body": "Gate code 4821"})
        entry = AuditLogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Note)
        ).latest("pk")
        self.assertEqual((entry.action, entry.user), ("created", self.casey))


class WhatTheJobPageShowsTests(TestCase):
    """The owner's choice, asserted in both directions."""

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("riley"), Role.SALES_REP)
        self.casey = grant_role(f.user("casey"), Role.CLEANER)
        self.customer = f.contact(self.owner)
        self.job = f.job(self.customer, self.owner)
        f.assign(self.job, self.casey)
        self.job_note = Note.objects.create(body="Gate code 4821", author=self.casey, job=self.job)
        self.customer_note = Note.objects.create(
            body="Prefers a morning slot", author=self.rep, contact=self.customer
        )
        self.unrelated = Note.objects.create(body="Van needs a service", author=self.owner)

    def shown(self, username):
        self.client.login(username=username, password=PASSWORD)
        response = self.client.get(self.job.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        return response

    def test_a_crew_member_sees_notes_about_the_job_and_the_customer(self):
        """The owner chose the wider view: standing at the house, what
        is known about the household is useful."""
        response = self.shown("casey")
        self.assertContains(response, "Gate code 4821")
        self.assertContains(response, "Prefers a morning slot")

    def test_a_crew_member_sees_customer_notes_from_a_job_at_another_address(self):
        """What the warning on the form actually promises.

        The job page filters customer notes by **contact**, not by
        address. A customer with two addresses therefore has their
        notes readable by a crew member on either job. Asserted because
        review found the warning describing it as address-scoped, and
        nothing here contradicted that.
        """
        from apps.crm.models import Property

        second = Property.objects.create(
            contact=self.customer,
            street="99 Other St",
            city="Rochester",
            state="NY",
            postal_code="14610",
        )
        elsewhere = f.job(
            self.customer,
            self.owner,
            start=timezone.now() + timedelta(days=3),
            service_property=second,
        )
        f.assign(elsewhere, self.casey)
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.get(elsewhere.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prefers a morning slot")

    def test_an_unrelated_note_is_not_shown(self):
        """ "Wider" is not "everything"."""
        self.assertNotContains(self.shown("casey"), "Van needs a service")

    def test_a_customer_note_is_marked_as_such(self):
        """So a crew member can tell which notes are about today's work
        and which are about the household generally."""
        self.assertContains(self.shown("casey"), "about the customer")

    def test_a_crew_member_still_cannot_reach_the_notes_list(self):
        """It spans every customer. Seeing one household's notes at
        their door is not the same as browsing the book."""
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("crm:note_list")).status_code, 403)

    def test_a_crew_member_cannot_edit_any_note(self):
        """`users/0004` gives them `add_note` and nothing more, so they
        can leave a note and cannot go back and change what it said —
        not even their own."""
        self.client.login(username="casey", password=PASSWORD)
        for note in (self.job_note, self.customer_note):
            response = self.client.get(reverse("crm:note_update", args=[note.pk]))
            self.assertEqual(response.status_code, 403, note.body)

    def test_a_crew_member_cannot_write_a_general_note_from_the_hub(self):
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("crm:note_create")).status_code, 403)


class AccessTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("riley"), Role.SALES_REP)
        self.note = Note.objects.create(body="Something", author=self.owner)

    def test_a_sales_rep_can_write_and_edit_notes(self):
        self.client.login(username="riley", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("crm:note_create")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("crm:note_update", args=[self.note.pk])).status_code, 200
        )

    def test_a_signed_out_visitor_is_sent_to_sign_in(self):
        for url in (
            reverse("crm:note_create"),
            reverse("crm:note_update", args=[self.note.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_someone_with_no_role_is_refused(self):
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_user("nobody", password=PASSWORD)
        self.client.login(username="nobody", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("crm:note_create")).status_code, 403)
