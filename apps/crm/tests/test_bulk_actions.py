"""Doing one thing to a page of records at once (Phase 22).

Two rules carry most of these tests:

1. **The count has to be true.** Every action skips the records already
   in the state asked for, so each fixture here deliberately mixes
   records that need the change with records that don't — if the code
   counted the whole selection, the message would read a different
   number and the test fails on it.
2. **It is the same rule as the single-record button, not a second
   one.** Completing a follow-up has to log the customer touch that
   resets their repeat-service clock; deactivating has to write the
   change log entry that `apps/crm/undo.py` can put back. Both are
   asserted against the behaviour, not against the implementation.
"""

from datetime import timedelta

from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm import bulk, undo
from apps.crm.models import Activity, AuditLogEntry, Contact, Tag, Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"
CONTACT_BULK = reverse("crm:contact_bulk")
TASK_BULK = reverse("crm:task_bulk")
CONTACT_LIST = reverse("crm:contact_list")
TASK_LIST = reverse("crm:task_list")


def said(response):
    """The one message the page came back with."""
    notes = [str(message) for message in response.context["messages"]]
    assert len(notes) == 1, notes
    return notes[0]


class BulkTestCase(TestCase):
    def setUp(self):
        self.rep = grant_role(f.user("rep"), Role.SALES_REP)
        self.client.login(username="rep", password=PASSWORD)

    def post(self, url, action, records=(), **extra):
        data = {"action": action, "selected": [record.pk for record in records]}
        data.update(extra)
        return self.client.post(url, data, follow=True)


class TaggingTests(BulkTestCase):
    def setUp(self):
        super().setUp()
        self.spring = Tag.objects.create(name="Spring 2027")
        self.gutters = Tag.objects.create(name="Gutters")
        self.pat = f.contact(self.rep, "Pat", "Homeowner")
        self.sam = f.contact(self.rep, "Sam", "Renter")
        self.lee = f.contact(self.rep, "Lee", "Landlord")
        self.pat.tags.add(self.spring)

    def test_only_the_ones_that_needed_it_are_counted(self):
        """Pat already has the tag. "Added to 3 customers" would be the
        number the owner sees and believes."""
        response = self.post(
            CONTACT_BULK, "tag", [self.pat, self.sam, self.lee], tag=self.spring.pk
        )
        self.assertEqual(
            said(response), "Added “Spring 2027” to 2 customers. 1 customer already had it."
        )
        for contact in (self.sam, self.lee):
            self.assertTrue(contact.tags.filter(pk=self.spring.pk).exists(), contact)

    def test_removing_one_tag_leaves_the_others_alone(self):
        """The obvious wrong implementation is `tags.clear()`."""
        self.pat.tags.add(self.gutters)
        self.post(CONTACT_BULK, "untag", [self.pat], tag=self.spring.pk)
        self.assertEqual([tag.name for tag in self.pat.tags.all()], ["Gutters"])

    def test_untagging_counts_only_the_ones_that_had_it(self):
        response = self.post(CONTACT_BULK, "untag", [self.pat, self.sam], tag=self.spring.pk)
        self.assertEqual(
            said(response), "Removed “Spring 2027” from 1 customer. 1 customer did not have it."
        )
        self.assertFalse(self.pat.tags.exists())

    def test_a_tag_action_with_no_tag_chosen_changes_nothing(self):
        """Not a silent no-op: picking "Add tag" and forgetting the tag
        is the likeliest mistake at this bar, and it has to say so."""
        response = self.post(CONTACT_BULK, "tag", [self.sam, self.lee])
        self.assertEqual(said(response), "Choose a tag as well.")
        self.assertFalse(self.sam.tags.exists())
        self.assertEqual(AuditLogEntry.objects.count(), 0)

    def test_the_log_entry_records_the_whole_list_before_and_after(self):
        """`tags: Gutters → Gutters, Spring 2027` rather than "tags
        changed" — the point of the log is being able to see what it
        was."""
        self.sam.tags.add(self.gutters)
        self.post(CONTACT_BULK, "tag", [self.sam], tag=self.spring.pk)
        entry = AuditLogEntry.objects.get(object_id=self.sam.pk)
        self.assertEqual(entry.changes, {"tags": ["Gutters", "Gutters, Spring 2027"]})
        self.assertEqual(entry.user, self.rep)

    def test_a_tag_change_says_plainly_that_it_cannot_be_undone(self):
        """Contacts *are* undoable and `tags` is written into their log,
        so this is the case where undo has to refuse rather than guess
        at a many-to-many (apps/crm/undo.py)."""
        self.post(CONTACT_BULK, "tag", [self.sam], tag=self.spring.pk)
        entry = AuditLogEntry.objects.get(object_id=self.sam.pk)
        self.assertFalse(undo.can_undo(entry))
        self.assertIn("tags", undo.why_not(entry))


class ActivationTests(BulkTestCase):
    def setUp(self):
        super().setUp()
        self.pat = f.contact(self.rep, "Pat", "Homeowner")
        self.sam = f.contact(self.rep, "Sam", "Renter")
        self.gone = f.contact(self.rep, "Lee", "Moved", is_active=False)

    def test_only_the_active_ones_are_deactivated(self):
        response = self.post(CONTACT_BULK, "deactivate", [self.pat, self.sam, self.gone])
        self.assertEqual(
            said(response), "Deactivated 2 customers. 1 customer was already inactive."
        )
        self.assertEqual(Contact.objects.filter(is_active=True).count(), 0)

    def test_only_the_inactive_ones_are_reactivated(self):
        response = self.post(CONTACT_BULK, "reactivate", [self.pat, self.gone])
        self.assertEqual(said(response), "Reactivated 1 customer. 1 customer was already active.")
        self.gone.refresh_from_db()
        self.assertTrue(self.gone.is_active)

    def test_the_message_reads_as_English_for_more_than_one(self):
        """Every other count here happens to be one, so "2 customers
        was already inactive" would go unnoticed."""
        second_gone = f.contact(self.rep, "Dee", "Gone", is_active=False)
        response = self.post(CONTACT_BULK, "deactivate", [self.pat, self.gone, second_gone])
        self.assertEqual(
            said(response), "Deactivated 1 customer. 2 customers were already inactive."
        )

    def test_one_log_entry_per_customer_changed_and_none_for_the_rest(self):
        self.post(CONTACT_BULK, "deactivate", [self.pat, self.sam, self.gone])
        self.assertEqual(AuditLogEntry.objects.count(), 2)
        self.assertFalse(AuditLogEntry.objects.filter(object_id=self.gone.pk).exists())
        entry = AuditLogEntry.objects.get(object_id=self.pat.pk)
        self.assertEqual(entry.changes, {"is_active": ["True", "False"]})

    def test_being_deactivated_in_a_batch_is_as_undoable_as_on_its_own(self):
        """The reason the entry is written in exactly the shape
        `ContactDeactivateView` writes: a customer's own page can put
        this back, whichever way it happened."""
        self.post(CONTACT_BULK, "deactivate", [self.pat])
        entry = AuditLogEntry.objects.get(object_id=self.pat.pk)
        self.assertIsNone(undo.why_not(entry))
        undo.undo(entry, self.rep)
        self.pat.refresh_from_db()
        self.assertTrue(self.pat.is_active)


class RefusalTests(BulkTestCase):
    def setUp(self):
        super().setUp()
        self.pat = f.contact(self.rep, "Pat", "Homeowner")

    def test_an_action_nobody_offered_changes_nothing(self):
        response = self.post(CONTACT_BULK, "delete", [self.pat])
        self.assertEqual(said(response), "Choose what to do with them first.")
        self.pat.refresh_from_db()
        self.assertTrue(self.pat.is_active)
        self.assertEqual(Contact.objects.count(), 1)

    def test_nothing_ticked_says_what_to_do(self):
        response = self.post(CONTACT_BULK, "deactivate")
        self.assertEqual(said(response), "Tick the customers you want to change first.")

    def test_more_than_a_full_page_at_once_is_refused(self):
        """The ids come from a form post, so the selection is whatever
        was sent — this is what keeps "never load an unbounded set"
        true here."""
        Contact.objects.bulk_create(
            Contact(first_name=f"Many {number}", last_name="Posted", created_by=self.rep)
            for number in range(bulk.MAX_RECORDS + 1)
        )
        posted = Contact.objects.filter(last_name="Posted")
        response = self.client.post(
            CONTACT_BULK,
            {"action": "deactivate", "selected": list(posted.values_list("pk", flat=True))},
            follow=True,
        )
        self.assertIn(f"more than {bulk.MAX_RECORDS}", said(response))
        self.assertEqual(posted.filter(is_active=False).count(), 0)

    def test_an_id_that_is_not_a_number_is_dropped(self):
        response = self.client.post(
            CONTACT_BULK,
            {"action": "deactivate", "selected": ["not-an-id", str(self.pat.pk)]},
            follow=True,
        )
        self.assertEqual(said(response), "Deactivated 1 customer.")

    def test_an_id_for_a_record_that_is_gone_is_simply_not_found(self):
        missing = self.pat.pk + 1000
        response = self.client.post(
            CONTACT_BULK, {"action": "deactivate", "selected": [missing]}, follow=True
        )
        self.assertEqual(said(response), "Tick the customers you want to change first.")


class TaskActionTests(BulkTestCase):
    def setUp(self):
        super().setUp()
        self.customer = f.contact(self.rep, "Pat", "Homeowner")
        self.first = self.task("Ring Pat back")
        self.second = self.task("Quote the gutters")

    def task(self, title, **extra):
        return Task.objects.create(title=title, assigned_to=self.rep, created_by=self.rep, **extra)

    def test_completing_several_records_the_date_and_who_did_it(self):
        response = self.post(TASK_BULK, "complete", [self.first, self.second])
        self.assertEqual(said(response), "Completed 2 tasks.")
        for task in (self.first, self.second):
            task.refresh_from_db()
            self.assertEqual(task.status, Task.Status.COMPLETED)
            self.assertIsNotNone(task.completed_at, task.title)
            self.assertEqual(task.completed_by, self.rep)

    def test_a_cancelled_task_in_the_selection_is_left_alone(self):
        """The rule `TaskCompleteView` enforces for one task. A ticked
        page of twenty is exactly where a cancelled one hides, and
        completing it would revive something somebody called off."""
        cancelled = self.task("Dropped", status=Task.Status.CANCELLED)
        response = self.post(TASK_BULK, "complete", [self.first, cancelled])
        self.assertEqual(
            said(response), "Completed 1 task. 1 task was not pending and was left alone."
        )
        cancelled.refresh_from_db()
        self.assertEqual(cancelled.status, Task.Status.CANCELLED)
        self.assertIsNone(cancelled.completed_at)

    def test_an_already_completed_task_keeps_its_original_completion(self):
        """Re-completing would re-stamp the date and the person, so a
        task finished last week by somebody else would look like mine,
        today."""
        other = grant_role(f.user("other"), Role.SALES_REP)
        then = timezone.now() - timedelta(days=7)
        done = self.task("Already done", status=Task.Status.COMPLETED, completed_by=other)
        Task.objects.filter(pk=done.pk).update(completed_at=then)

        response = self.post(TASK_BULK, "complete", [done])
        self.assertEqual(said(response), "1 task was not pending and was left alone.")
        done.refresh_from_db()
        self.assertEqual(done.completed_by, other)
        self.assertEqual(done.completed_at, then)

    def test_completing_a_follow_up_still_resets_the_customers_clock(self):
        """The whole reason this goes through `apps/crm/completion.py`.
        Setting `status` directly would mark the follow-up done and
        leave the customer due for the same call tomorrow."""
        follow_up = self.task(
            "Check in about gutters",
            kind=Task.Kind.FOLLOW_UP,
            contact=self.customer,
            service_type=f.service(),
        )
        self.post(TASK_BULK, "complete", [follow_up])
        touches = Activity.objects.filter(
            contact=self.customer, activity_type=Activity.ActivityType.FOLLOW_UP
        )
        self.assertEqual(touches.count(), 1)
        self.assertEqual(touches.get().created_by, self.rep)

    def test_cancelling_clears_any_completion_left_on_the_task(self):
        """`completed_at` is what every count of finished work reads, so
        a cancelled task still holding one is counted as done
        (docs/DATABASE_DESIGN.md calls this an application-layer
        invariant).

        The stale stamp is put there on purpose. A pending task has no
        completion date, so cancelling one and finding none proves
        nothing — the assertion would hold however the code behaved.
        """
        Task.objects.filter(pk=self.first.pk).update(
            completed_at=timezone.now() - timedelta(days=3), completed_by=self.rep
        )
        response = self.post(TASK_BULK, "cancel", [self.first, self.second])
        self.assertEqual(said(response), "Cancelled 2 tasks.")
        for task in (self.first, self.second):
            task.refresh_from_db()
            self.assertEqual(task.status, Task.Status.CANCELLED)
            self.assertIsNone(task.completed_at, task.title)
            self.assertIsNone(task.completed_by, task.title)

    def test_cancelling_does_not_log_a_customer_touch(self):
        follow_up = self.task(
            "Check in about gutters",
            kind=Task.Kind.FOLLOW_UP,
            contact=self.customer,
            service_type=f.service(),
        )
        self.post(TASK_BULK, "cancel", [follow_up])
        self.assertFalse(Activity.objects.filter(contact=self.customer).exists())

    def test_each_task_changed_gets_the_same_log_entry_the_button_writes(self):
        self.post(TASK_BULK, "complete", [self.first])
        entry = AuditLogEntry.objects.get(object_id=self.first.pk)
        self.assertEqual(entry.changes, {"status": ["Pending", "Completed"]})
        self.assertEqual(entry.user, self.rep)

    def test_cancelling_logs_the_status_it_moved_to(self):
        """The two actions share one helper, so a hard-coded
        "Completed" in that log line would be invisible from the
        complete tests."""
        self.post(TASK_BULK, "cancel", [self.first])
        entry = AuditLogEntry.objects.get(object_id=self.first.pk)
        self.assertEqual(entry.changes, {"status": ["Pending", "Cancelled"]})


class PageTests(BulkTestCase):
    def setUp(self):
        super().setUp()
        self.pat = f.contact(self.rep, "Pat", "Homeowner")
        self.task = Task.objects.create(
            title="Ring Pat back", assigned_to=self.rep, created_by=self.rep
        )

    def test_the_customer_list_offers_the_bar_and_a_box_per_row(self):
        response = self.client.get(CONTACT_LIST)
        self.assertContains(response, f'value="{self.pat.pk}"')
        self.assertContains(response, 'name="selected"')
        self.assertContains(response, CONTACT_BULK)
        self.assertContains(response, "With the ticked customers")

    def test_the_task_list_offers_the_bar_and_a_box_per_row(self):
        response = self.client.get(TASK_LIST)
        self.assertContains(response, 'name="selected"')
        self.assertContains(response, TASK_BULK)

    def test_both_lists_offer_every_action_the_endpoint_accepts(self):
        """A dropdown offering something the view refuses, or missing
        something it accepts, is a bar that half works."""
        customers = self.client.get(CONTACT_LIST)
        for value, label in bulk.CONTACT_ACTIONS:
            self.assertContains(customers, f'value="{value}"')
            self.assertContains(customers, label)
        tasks = self.client.get(TASK_LIST)
        for value, label in bulk.TASK_ACTIONS:
            self.assertContains(tasks, f'value="{value}"')
            self.assertContains(tasks, label)

    def test_it_comes_back_to_the_page_you_were_looking_at(self):
        """Filters survive the round trip, or acting on a filtered list
        means finding it again afterwards."""
        filtered = f"{CONTACT_LIST}?status=active&q=Pat"
        response = self.client.post(
            CONTACT_BULK,
            {"action": "deactivate", "selected": [self.pat.pk], "next": filtered},
        )
        self.assertRedirects(response, filtered)

    def test_a_next_pointing_off_this_site_is_refused(self):
        response = self.client.post(
            CONTACT_BULK,
            {"action": "deactivate", "selected": [self.pat.pk], "next": "https://evil.test/"},
        )
        self.assertRedirects(response, CONTACT_LIST)

    def test_a_get_cannot_change_anything(self):
        """A link that deactivates twenty customers is one crawler away
        from doing it unasked."""
        for url in (CONTACT_BULK, TASK_BULK):
            self.assertEqual(self.client.get(url).status_code, 405, url)
        self.pat.refresh_from_db()
        self.assertTrue(self.pat.is_active)

    def test_a_post_without_the_csrf_token_is_refused(self):
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="rep", password=PASSWORD)
        response = strict.post(CONTACT_BULK, {"action": "deactivate", "selected": [self.pat.pk]})
        self.assertEqual(response.status_code, 403)
        self.pat.refresh_from_db()
        self.assertTrue(self.pat.is_active)

    def test_a_cleaner_is_refused_both_endpoints(self):
        grant_role(f.user("crew"), Role.CLEANER)
        self.client.login(username="crew", password=PASSWORD)
        for url, record in ((CONTACT_BULK, self.pat), (TASK_BULK, self.task)):
            response = self.client.post(url, {"action": "cancel", "selected": [record.pk]})
            self.assertEqual(response.status_code, 403, url)
        self.pat.refresh_from_db()
        self.task.refresh_from_db()
        self.assertTrue(self.pat.is_active)
        self.assertEqual(self.task.status, Task.Status.PENDING)

    def test_without_the_change_permission_there_is_no_bar_and_no_endpoint(self):
        """The bar is gated on the permission the endpoint requires, so
        the two can't drift into showing a button that 403s."""
        group = Group.objects.get(name=Role.SALES_REP.value)
        group.permissions.remove(Permission.objects.get(codename="change_contact"))

        response = self.client.get(CONTACT_LIST)
        self.assertNotContains(response, 'name="selected"')
        self.assertEqual(
            self.client.post(
                CONTACT_BULK, {"action": "deactivate", "selected": [self.pat.pk]}
            ).status_code,
            403,
        )
