from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Notification
from apps.core.notifications import bell, mark_all_read, notify
from apps.crm.models import Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"
LIST_URL = reverse("core:notifications")


def make(recipient, title="Something happened", **extra):
    extra.setdefault("kind", Notification.Kind.TASK)
    return Notification.objects.create(recipient=recipient, title=title, **extra)


class NotifyTests(TestCase):
    def setUp(self):
        self.user = grant_role(f.user("alice"), Role.SALES_REP)

    def test_an_event_key_announces_once(self):
        first = notify(self.user, Notification.Kind.FOLLOW_UP, "Follow-up due", event="task:1")
        again = notify(self.user, Notification.Kind.FOLLOW_UP, "Follow-up due", event="task:1")
        self.assertIsNotNone(first)
        self.assertIsNone(again)
        self.assertEqual(Notification.objects.count(), 1)

    def test_without_a_key_each_call_announces(self):
        notify(self.user, Notification.Kind.TASK, "Assigned")
        notify(self.user, Notification.Kind.TASK, "Assigned")
        self.assertEqual(Notification.objects.count(), 2)

    def test_the_same_key_for_two_people_is_two_notifications(self):
        other = grant_role(f.user("bob"), Role.SALES_REP)
        notify(self.user, Notification.Kind.TASK, "Shared", event="task:7")
        notify(other, Notification.Kind.TASK, "Shared", event="task:7")
        self.assertEqual(Notification.objects.count(), 2)

    def test_nobody_to_tell_is_not_an_error(self):
        self.assertIsNone(notify(None, Notification.Kind.SYSTEM, "Into the void"))
        self.assertFalse(Notification.objects.exists())

    def test_long_text_is_trimmed_to_fit(self):
        notification = notify(self.user, Notification.Kind.SYSTEM, "T" * 300, "B" * 400)
        self.assertEqual((len(notification.title), len(notification.body)), (160, 300))


class BellTests(TestCase):
    def setUp(self):
        self.user = grant_role(f.user("alice"), Role.SALES_REP)
        self.client.login(username="alice", password=PASSWORD)

    def test_the_bell_counts_only_unread_and_shows_the_newest_first(self):
        old = make(self.user, "Older")
        new = make(self.user, "Newer")
        seen = make(self.user, "Already seen", read_at=timezone.now())
        data = bell(self.user)
        # Read ones still show — the bell is a short history, not a queue.
        self.assertEqual(data["unread"], 2)
        self.assertEqual([n.pk for n in data["items"]], [seen.pk, new.pk, old.pk])

    def test_the_bell_holds_at_most_eight(self):
        for index in range(10):
            make(self.user, f"Notice {index}")
        self.assertEqual(len(bell(self.user)["items"]), 8)

    def test_the_bell_only_ever_shows_your_own(self):
        other = grant_role(f.user("bob"), Role.SALES_REP)
        make(other, "Not yours")
        self.assertEqual(bell(self.user), {"unread": 0, "items": []})

    def test_the_bell_appears_in_the_page_with_its_count(self):
        make(self.user, "Roof quote accepted")
        page = self.client.get(reverse("core:index")).content.decode()
        self.assertIn("bell-dot", page)
        self.assertIn("Roof quote accepted", page)

    def test_a_user_with_no_role_gets_no_bell(self):
        f.user("nobody")
        self.client.login(username="nobody", password=PASSWORD)
        self.assertNotContains(self.client.get(reverse("core:index")), "bell-button")


class NotificationPageTests(TestCase):
    def setUp(self):
        self.user = grant_role(f.user("alice"), Role.SALES_REP)
        self.other = grant_role(f.user("bob"), Role.SALES_REP)
        self.client.login(username="alice", password=PASSWORD)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(LIST_URL).status_code, 302)

    def test_the_list_shows_your_own_only(self):
        make(self.user, "Yours")
        make(self.other, "Theirs")
        response = self.client.get(LIST_URL)
        self.assertContains(response, "Yours")
        self.assertNotContains(response, "Theirs")

    def test_empty_state(self):
        self.assertContains(self.client.get(LIST_URL), "No notifications yet")

    def test_opening_one_marks_it_read_and_follows_its_link(self):
        notification = make(self.user, "Task for you", url="/tasks/")
        response = self.client.post(reverse("core:notification_read", args=[notification.pk]))
        self.assertRedirects(response, "/tasks/", fetch_redirect_response=False)
        notification.refresh_from_db()
        self.assertFalse(notification.is_unread)

    def test_one_without_a_link_returns_to_the_list(self):
        notification = make(self.user, "Nothing to open")
        response = self.client.post(reverse("core:notification_read", args=[notification.pk]))
        self.assertRedirects(response, LIST_URL)

    def test_someone_elses_notification_is_not_found(self):
        notification = make(self.other, "Theirs")
        response = self.client.post(reverse("core:notification_read", args=[notification.pk]))
        self.assertEqual(response.status_code, 404)
        notification.refresh_from_db()
        self.assertTrue(notification.is_unread)

    def test_mark_all_read_only_touches_your_own(self):
        make(self.user, "Mine")
        theirs = make(self.other, "Theirs")
        self.client.post(reverse("core:notifications_read_all"))
        self.assertEqual(mark_all_read(self.user), 0)  # nothing left unread
        theirs.refresh_from_db()
        self.assertTrue(theirs.is_unread)

    def test_mark_all_read_returns_where_it_came_from_but_only_on_this_site(self):
        make(self.user, "Mine")
        here = self.client.post(reverse("core:notifications_read_all"), {"next": "/calendar/"})
        self.assertRedirects(here, "/calendar/", fetch_redirect_response=False)
        make(self.user, "Another")
        away = self.client.post(
            reverse("core:notifications_read_all"), {"next": "https://evil.example.com/"}
        )
        self.assertRedirects(away, LIST_URL)


class TaskProducerTests(TestCase):
    """The events that actually raise a notification today."""

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("rep", first_name="Robin", last_name="Reyes"), Role.SALES_REP)
        self.client.login(username="boss", password=PASSWORD)
        self.contact = f.contact(self.owner)

    def form(self, **extra):
        data = {
            "title": "Call the customer back",
            "kind": Task.Kind.GENERAL,
            "status": Task.Status.PENDING,
            "priority": Task.Priority.MEDIUM,
            "assigned_to": self.rep.pk,
            "contact": self.contact.pk,
        }
        data.update(extra)
        return data

    def test_assigning_a_task_to_someone_else_tells_them(self):
        self.client.post(reverse("crm:task_create"), self.form())
        notification = Notification.objects.get(recipient=self.rep)
        self.assertEqual(notification.kind, Notification.Kind.TASK)
        self.assertIn("boss", notification.title)
        self.assertEqual(notification.body, "Call the customer back")
        self.assertTrue(notification.url.startswith("/"))

    def test_assigning_a_task_to_yourself_tells_nobody(self):
        self.client.post(reverse("crm:task_create"), self.form(assigned_to=self.owner.pk))
        self.assertFalse(Notification.objects.exists())

    def test_editing_a_task_without_reassigning_it_tells_nobody_again(self):
        self.client.post(reverse("crm:task_create"), self.form())
        task = Task.objects.get()
        Notification.objects.all().delete()
        self.client.post(
            reverse("crm:task_update", args=[task.pk]), self.form(title="Call them this afternoon")
        )
        self.assertFalse(Notification.objects.exists())

    def test_reassigning_a_task_tells_the_new_owner(self):
        self.client.post(reverse("crm:task_create"), self.form())
        task = Task.objects.get()
        Notification.objects.all().delete()
        third = grant_role(f.user("sam"), Role.SALES_REP)
        self.client.post(
            reverse("crm:task_update", args=[task.pk]), self.form(assigned_to=third.pk)
        )
        self.assertEqual([n.recipient for n in Notification.objects.all()], [third])
