from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.crm.models import Contact, Task
from apps.jobs.tests import _factories as jf

User = get_user_model()


class TaskModelTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user("creator", password="pw")
        self.assignee = User.objects.create_user("assignee", password="pw")

    def test_create_task_with_defaults(self):
        task = Task.objects.create(
            title="Call back", assigned_to=self.assignee, created_by=self.creator
        )
        self.assertEqual(task.status, Task.Status.PENDING)
        self.assertEqual(task.priority, Task.Priority.MEDIUM)
        self.assertIsNone(task.contact)
        self.assertIsNone(task.quote)

    def test_task_with_neither_contact_nor_estimate_is_allowed(self):
        # Task has no "at least one relation" DB rule — a plain to-do
        # with no CRM object attached is valid. (Activity doesn't have
        # this rule either since docs/DATABASE_REVIEW.md finding #2 —
        # see test_activity.py.)
        task = Task.objects.create(
            title="Follow up on inbox", assigned_to=self.assignee, created_by=self.creator
        )
        self.assertIsNone(task.contact)
        self.assertIsNone(task.quote)

    def test_assigned_to_is_required(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Task.objects.create(title="No assignee", created_by=self.creator)

    def test_contact_deletion_sets_null(self):
        contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.creator
        )
        task = Task.objects.create(
            title="Follow up",
            assigned_to=self.assignee,
            contact=contact,
            created_by=self.creator,
        )
        contact.delete()
        task.refresh_from_db()
        self.assertIsNone(task.contact)

    def test_estimate_deletion_sets_null(self):
        """`quote` replaced `deal` here when Phase 17 folded the two.

        Same invariant, on the field that still exists: losing the
        estimate must not take the task with it. SET_NULL only holds
        through the ORM — every foreign key in this schema is NO ACTION
        in PostgreSQL (docs/DATABASE_REVIEW.md finding #1) — so this
        deletes through `Model.delete()`, which is the only path the
        app ever uses.
        """
        customer = jf.contact(self.creator)
        quote = jf.quote(customer, self.creator)
        task = Task.objects.create(
            title="Follow up", assigned_to=self.assignee, quote=quote, created_by=self.creator
        )
        quote.delete()
        task.refresh_from_db()
        self.assertIsNone(task.quote)
