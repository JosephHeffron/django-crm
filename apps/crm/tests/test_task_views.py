import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Company, Contact, Deal, Task
from apps.crm.tests._helpers import grant_role

User = get_user_model()


class TaskListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_role(self.user)
        self.other_user = User.objects.create_user("bob", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:task_list"))
        self.assertEqual(response.status_code, 302)

    def test_empty_list_shows_no_tasks_message(self):
        response = self.client.get(reverse("crm:task_list"))
        self.assertContains(response, "No tasks found")

    def test_status_filter(self):
        Task.objects.create(
            title="Pending one",
            assigned_to=self.user,
            created_by=self.user,
            status=Task.Status.PENDING,
        )
        Task.objects.create(
            title="Done one",
            assigned_to=self.user,
            created_by=self.user,
            status=Task.Status.COMPLETED,
        )
        response = self.client.get(reverse("crm:task_list"), {"status": "completed"})
        titles = [t.title for t in response.context["tasks"]]
        self.assertEqual(titles, ["Done one"])

    def test_invalid_status_param_is_ignored(self):
        Task.objects.create(title="A task", assigned_to=self.user, created_by=self.user)
        response = self.client.get(reverse("crm:task_list"), {"status": "not-a-real-status"})
        self.assertEqual(response.status_code, 200)
        titles = [t.title for t in response.context["tasks"]]
        self.assertEqual(titles, ["A task"])

    def test_priority_filter(self):
        Task.objects.create(
            title="Urgent", assigned_to=self.user, created_by=self.user, priority=Task.Priority.HIGH
        )
        Task.objects.create(
            title="Whenever",
            assigned_to=self.user,
            created_by=self.user,
            priority=Task.Priority.LOW,
        )
        response = self.client.get(reverse("crm:task_list"), {"priority": "high"})
        titles = [t.title for t in response.context["tasks"]]
        self.assertEqual(titles, ["Urgent"])

    def test_mine_filter(self):
        Task.objects.create(title="Mine", assigned_to=self.user, created_by=self.user)
        Task.objects.create(title="Not mine", assigned_to=self.other_user, created_by=self.user)
        response = self.client.get(reverse("crm:task_list"), {"mine": "1"})
        titles = [t.title for t in response.context["tasks"]]
        self.assertEqual(titles, ["Mine"])

    def test_overdue_filter(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        Task.objects.create(
            title="Overdue", assigned_to=self.user, created_by=self.user, due_date=yesterday
        )
        Task.objects.create(
            title="Not yet due", assigned_to=self.user, created_by=self.user, due_date=tomorrow
        )
        Task.objects.create(
            title="Overdue but completed",
            assigned_to=self.user,
            created_by=self.user,
            due_date=yesterday,
            status=Task.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        response = self.client.get(reverse("crm:task_list"), {"overdue": "1"})
        titles = [t.title for t in response.context["tasks"]]
        self.assertEqual(titles, ["Overdue"])


class TaskCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_role(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.user
        )
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)
        self.deal = Deal.objects.create(
            title="Acme deal", company=self.company, created_by=self.user
        )

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:task_create"))
        self.assertEqual(response.status_code, 302)

    def test_get_defaults_assigned_to_current_user(self):
        response = self.client.get(reverse("crm:task_create"))
        self.assertEqual(response.context["form"].initial.get("assigned_to"), self.user.pk)

    def test_get_prefills_relation_from_query_param(self):
        response = self.client.get(reverse("crm:task_create"), {"contact": self.contact.pk})
        self.assertEqual(response.context["form"].initial.get("contact"), self.contact.pk)

    def test_get_with_invalid_query_param_does_not_error(self):
        response = self.client.get(reverse("crm:task_create"), {"deal": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("deal", response.context["form"].initial)

    def test_create_sets_created_by(self):
        response = self.client.post(
            reverse("crm:task_create"),
            {
                "title": "Follow up",
                "assigned_to": self.user.pk,
                "priority": "medium",
                "status": "pending",
            },
        )
        task = Task.objects.get(title="Follow up")
        self.assertRedirects(response, task.get_absolute_url())
        self.assertEqual(task.created_by, self.user)

    def test_create_with_completed_status_sets_completed_at(self):
        self.client.post(
            reverse("crm:task_create"),
            {
                "title": "Already done",
                "assigned_to": self.user.pk,
                "priority": "medium",
                "status": "completed",
            },
        )
        task = Task.objects.get(title="Already done")
        self.assertIsNotNone(task.completed_at)


class TaskUpdateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_role(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.task = Task.objects.create(
            title="Original", assigned_to=self.user, created_by=self.user
        )

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("crm:task_update", args=[self.task.pk]))
        self.assertEqual(response.status_code, 302)

    def test_update_to_completed_sets_completed_at(self):
        self.client.post(
            reverse("crm:task_update", args=[self.task.pk]),
            {
                "title": "Original",
                "assigned_to": self.user.pk,
                "priority": "medium",
                "status": "completed",
            },
        )
        self.task.refresh_from_db()
        self.assertIsNotNone(self.task.completed_at)

    def test_reopening_clears_completed_at(self):
        self.task.status = Task.Status.COMPLETED
        self.task.completed_at = timezone.now()
        self.task.save()

        self.client.post(
            reverse("crm:task_update", args=[self.task.pk]),
            {
                "title": "Original",
                "assigned_to": self.user.pk,
                "priority": "medium",
                "status": "pending",
            },
        )
        self.task.refresh_from_db()
        self.assertIsNone(self.task.completed_at)


class TaskCompleteViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_role(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.task = Task.objects.create(title="Do it", assigned_to=self.user, created_by=self.user)

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.post(reverse("crm:task_complete", args=[self.task.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/accounts/login/"))

    def test_marks_task_completed(self):
        self.client.post(reverse("crm:task_complete", args=[self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.COMPLETED)
        self.assertIsNotNone(self.task.completed_at)

    def test_does_not_complete_a_cancelled_task(self):
        # A direct POST bypasses the UI, which only shows the "Mark
        # complete" action for pending tasks — the view itself must
        # not silently revive a cancelled task to completed.
        self.task.status = Task.Status.CANCELLED
        self.task.save()

        self.client.post(reverse("crm:task_complete", args=[self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.CANCELLED)
        self.assertIsNone(self.task.completed_at)

    def test_already_completed_task_is_left_unchanged(self):
        self.task.status = Task.Status.COMPLETED
        self.task.completed_at = timezone.now()
        self.task.save()
        original_completed_at = self.task.completed_at

        self.client.post(reverse("crm:task_complete", args=[self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.completed_at, original_completed_at)

    def test_redirects_to_task_detail_by_default(self):
        response = self.client.post(reverse("crm:task_complete", args=[self.task.pk]))
        self.assertRedirects(response, self.task.get_absolute_url())

    def test_redirects_to_safe_next_url(self):
        response = self.client.post(
            reverse("crm:task_complete", args=[self.task.pk]),
            {"next": reverse("crm:task_list")},
        )
        self.assertRedirects(response, reverse("crm:task_list"))

    def test_rejects_unsafe_next_url(self):
        response = self.client.post(
            reverse("crm:task_complete", args=[self.task.pk]),
            {"next": "https://evil.example.com/"},
        )
        self.assertRedirects(response, self.task.get_absolute_url())


class TaskDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_role(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.task = Task.objects.create(
            title="Check in", assigned_to=self.user, created_by=self.user
        )

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(self.task.get_absolute_url())
        self.assertEqual(response.status_code, 302)

    def test_shows_task_and_complete_action_when_pending(self):
        response = self.client.get(self.task.get_absolute_url())
        self.assertContains(response, "Check in")
        self.assertContains(response, reverse("crm:task_complete", args=[self.task.pk]))

    def test_hides_complete_action_when_already_completed(self):
        self.task.status = Task.Status.COMPLETED
        self.task.completed_at = timezone.now()
        self.task.save()
        response = self.client.get(self.task.get_absolute_url())
        self.assertNotContains(response, reverse("crm:task_complete", args=[self.task.pk]))


class TaskLinkedFromRelatedDetailPagesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        grant_role(self.user)
        self.client.login(username="alice", password="correct-horse-battery")
        self.contact = Contact.objects.create(
            first_name="Ada", last_name="Lovelace", created_by=self.user
        )
        self.company = Company.objects.create(name="Acme Corp", created_by=self.user)
        self.deal = Deal.objects.create(
            title="Acme deal", company=self.company, created_by=self.user
        )

    def test_contact_detail_links_to_task(self):
        task = Task.objects.create(
            title="Call Ada", assigned_to=self.user, created_by=self.user, contact=self.contact
        )
        response = self.client.get(self.contact.get_absolute_url())
        self.assertContains(response, task.get_absolute_url())

    def test_deal_detail_links_to_task(self):
        task = Task.objects.create(
            title="Chase deal", assigned_to=self.user, created_by=self.user, deal=self.deal
        )
        response = self.client.get(self.deal.get_absolute_url())
        self.assertContains(response, task.get_absolute_url())


class TaskFormFieldTests(TestCase):
    """The estimate field, and customers listed so the order shows."""

    def setUp(self):
        self.user = User.objects.create_user("boss", password="correct-horse-battery")
        grant_role(self.user)
        self.client.login(username="boss", password="correct-horse-battery")

    def contact(self, first, last, **extra):
        return Contact.objects.create(
            first_name=first, last_name=last, created_by=self.user, **extra
        )

    def form(self, url=None):
        return self.client.get(url or reverse("crm:task_create")).context["form"]

    def customer_labels(self, form=None):
        """The real customers offered, without the placeholder choice.

        Filter on the value, not the label: the empty choice's label is
        "- Select an option -", which is perfectly truthy.
        """
        form = form or self.form()
        return [str(label) for value, label in form.fields["contact"].choices if value]

    def test_the_form_asks_for_an_estimate_not_a_deal(self):
        # Deals were folded into estimates in Phase 17, so the deal
        # dropdown could only ever render empty.
        fields = self.form().fields
        self.assertIn("quote", fields)
        self.assertNotIn("deal", fields)

    def test_the_estimate_list_is_not_empty_when_estimates_exist(self):
        from apps.jobs.models import Quote

        customer = self.contact("Pat", "Homeowner")
        quote = Quote.objects.create(contact=customer, prepared_by=self.user)
        self.assertIn(quote, self.form().fields["quote"].queryset)

    def test_an_estimate_chosen_on_the_form_is_kept(self):
        from apps.jobs.models import Quote

        customer = self.contact("Pat", "Homeowner")
        quote = Quote.objects.create(contact=customer, prepared_by=self.user)
        self.client.post(
            reverse("crm:task_create"),
            {
                "title": "Chase it up",
                "assigned_to": self.user.pk,
                "contact": customer.pk,
                "quote": quote.pk,
                "priority": Task.Priority.MEDIUM,
                "status": Task.Status.PENDING,
            },
        )
        self.assertEqual(Task.objects.get(title="Chase it up").quote_id, quote.pk)

    def test_a_task_still_naming_an_old_deal_keeps_it_through_an_edit(self):
        # The model field stays until Phase 18 removes it; an edit must
        # not quietly wipe a legacy row's deal.
        company = Company.objects.create(name="Acme", created_by=self.user)
        customer = self.contact("Pat", "Homeowner", company=company)
        deal = Deal.objects.create(
            title="Old deal", company=company, contact=customer, created_by=self.user
        )
        task = Task.objects.create(
            title="Legacy", assigned_to=self.user, created_by=self.user, deal=deal
        )
        self.client.post(
            reverse("crm:task_update", args=[task.pk]),
            {
                "title": "Legacy renamed",
                "assigned_to": self.user.pk,
                "priority": Task.Priority.MEDIUM,
                "status": Task.Status.PENDING,
            },
        )
        task.refresh_from_db()
        self.assertEqual((task.title, task.deal_id), ("Legacy renamed", deal.pk))

    def test_customers_are_listed_surname_first(self):
        self.contact("Daniel", "Adams")
        self.assertIn("Adams, Daniel", self.customer_labels())

    def test_customers_read_in_alphabetical_order(self):
        # Sorted by surname but shown "Daniel Adams", the list looked
        # random to anyone reading the first names.
        for first, last in (("Brian", "Anderson"), ("Daniel", "Adams"), ("Karen", "Allen")):
            self.contact(first, last)
        labels = self.customer_labels()
        self.assertEqual(labels, sorted(labels))
        self.assertEqual(labels, ["Adams, Daniel", "Allen, Karen", "Anderson, Brian"])

    def test_a_deactivated_customer_is_not_offered_for_a_new_task(self):
        self.contact("Gone", "Away", is_active=False)
        self.assertNotIn("Away, Gone", self.customer_labels())

    def test_a_deactivated_customer_is_still_offered_on_a_task_that_names_them(self):
        # Otherwise editing an old task silently drops its customer.
        customer = self.contact("Gone", "Away", is_active=False)
        task = Task.objects.create(
            title="Old", assigned_to=self.user, created_by=self.user, contact=customer
        )
        form = self.form(reverse("crm:task_update", args=[task.pk]))
        self.assertIn(customer, form.fields["contact"].queryset)
