from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Activity, BusinessPlan, Note, PlanChecklistItem, Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Quote
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"
HUB_URLS = [
    "crm:task_list",
    "crm:task_followups",
    "jobs:quote_list",
    "crm:plan_list",
    "crm:note_list",
]


class HubTestCase(TestCase):
    def setUp(self):
        self.rep = grant_role(f.user("rep"), Role.SALES_REP)
        self.other = grant_role(f.user("other"), Role.SALES_REP)
        self.client.login(username="rep", password=PASSWORD)
        self.customer = f.contact(self.rep, "Pat", "Gutters")

    def follow_up(self, assignee, service="gutter-cleaning", days_ago=0, **extra):
        return Task.objects.create(
            title=f"Follow up {service}",
            kind=Task.Kind.FOLLOW_UP,
            contact=extra.pop("contact", self.customer),
            service_type=f.service(service),
            assigned_to=assignee,
            created_by=assignee,
            due_date=timezone.localdate() - timedelta(days=days_ago),
            **extra,
        )


class HubAccessTests(HubTestCase):
    def test_every_tab_renders_with_the_tab_bar_for_sales_roles(self):
        for name in HUB_URLS:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)
            self.assertContains(response, 'aria-label="Tasks sections"')

    def test_cleaners_are_refused_every_tab(self):
        grant_role(f.user("crew"), Role.CLEANER)
        self.client.login(username="crew", password=PASSWORD)
        for name in HUB_URLS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_tab_counts_due_follow_ups_and_open_quotes(self):
        self.follow_up(self.rep, days_ago=1)
        self.follow_up(self.rep, service="window-washing-exterior")
        Task.objects.filter(pk=self.follow_up(self.other, service="mulching").pk).update(
            due_date=timezone.localdate() + timedelta(days=3)
        )
        f.quote(self.customer, self.rep, status=Quote.Status.SENT)
        f.quote(self.customer, self.rep, status=Quote.Status.ACCEPTED)
        tabs = {
            t["label"]: t["count"]
            for t in self.client.get(reverse("crm:task_list")).context["hub_tabs"]
        }
        self.assertEqual((tabs["Follow-ups"], tabs["Quotes"]), (2, 1))


class FollowUpTabTests(HubTestCase):
    def titles(self, **params):
        response = self.client.get(reverse("crm:task_followups"), params)
        return [t.service_type.slug for t in response.context["follow_ups"]]

    def test_open_by_default_oldest_due_first_and_mine(self):
        self.follow_up(self.rep, "mulching", days_ago=1)
        self.follow_up(self.other, "trimming", days_ago=5)
        done = self.follow_up(self.rep, "weed-removal", status=Task.Status.COMPLETED)
        Task.objects.filter(pk=done.pk).update(completed_at=timezone.now())
        self.assertEqual(self.titles(), ["trimming", "mulching"])
        self.assertEqual(self.titles(mine="1"), ["mulching"])
        self.assertEqual(self.titles(show="done"), ["weed-removal"])
        self.assertEqual(self.titles(show="nonsense"), ["trimming", "mulching"])

    def test_mark_done_logs_the_touch_and_returns_to_the_tab(self):
        task = self.follow_up(self.rep)
        back = reverse("crm:task_followups") + "?mine=1"
        response = self.client.post(reverse("crm:task_complete", args=[task.pk]), {"next": back})
        self.assertRedirects(response, back)
        self.assertTrue(
            Activity.objects.filter(contact=self.customer, activity_type="follow_up").exists()
        )

    def test_general_task_list_filters_by_kind(self):
        self.follow_up(self.rep)
        Task.objects.create(title="Order ladders", assigned_to=self.rep, created_by=self.rep)
        response = self.client.get(reverse("crm:task_list"), {"kind": "general"})
        self.assertEqual([t.title for t in response.context["tasks"]], ["Order ladders"])


class QuoteTabTests(HubTestCase):
    def numbers(self, **params):
        response = self.client.get(reverse("jobs:quote_list"), params)
        return {q.number for q in response.context["quotes"]}

    def test_open_by_default_status_filter_and_mine(self):
        draft = f.quote(self.customer, self.rep, status=Quote.Status.DRAFT)
        sent = f.quote(self.customer, self.other, status=Quote.Status.SENT)
        won = f.quote(self.customer, self.rep, status=Quote.Status.ACCEPTED)
        self.assertEqual(self.numbers(), {draft.number, sent.number})
        self.assertEqual(self.numbers(status="accepted"), {won.number})
        self.assertEqual(self.numbers(status="all"), {draft.number, sent.number, won.number})
        self.assertEqual(self.numbers(mine="1"), {draft.number})
        # Unknown status falls back to "open", and the page says so.
        response = self.client.get(reverse("jobs:quote_list"), {"status": "bogus"})
        self.assertEqual(response.context["status"], "open")
        self.assertEqual(self.numbers(status="bogus"), {draft.number, sent.number})


class PlanAndNoteTabTests(HubTestCase):
    def test_plans_show_checklist_progress_and_hide_done_by_default(self):
        plan = BusinessPlan.objects.create(
            title="Gutter guards",
            owner=self.rep,
            created_by=self.rep,
            status=BusinessPlan.Status.IN_PROGRESS,
        )
        for i, done in enumerate((True, True, False)):
            PlanChecklistItem.objects.create(plan=plan, text=f"Step {i}", is_done=done, position=i)
        BusinessPlan.objects.create(
            title="Old goal", owner=self.rep, created_by=self.rep, status=BusinessPlan.Status.DONE
        )
        response = self.client.get(reverse("crm:plan_list"))
        (listed,) = response.context["plans"]
        self.assertEqual(
            (listed.title, listed.item_count, listed.done_count), ("Gutter guards", 3, 2)
        )
        self.assertEqual(
            [
                p.title
                for p in self.client.get(reverse("crm:plan_list"), {"show": "done"}).context[
                    "plans"
                ]
            ],
            ["Old goal"],
        )
        detail = self.client.get(plan.get_absolute_url())
        self.assertContains(detail, "2 of 3 done")

    def test_notes_filter_by_subject_and_search(self):
        job = f.job(self.customer, self.rep)
        Note.objects.create(author=self.rep, body="Truck inspection", pinned=True)
        Note.objects.create(author=self.rep, body="Gate sticks", contact=self.customer)
        Note.objects.create(author=self.rep, body="Bring pole", job=job)

        def bodies(**params):
            response = self.client.get(reverse("crm:note_list"), params)
            return [n.body for n in response.context["notes"]]

        self.assertEqual(bodies()[0], "Truck inspection")  # pinned first
        self.assertEqual(bodies(about="general"), ["Truck inspection"])
        self.assertEqual(bodies(about="contact"), ["Gate sticks"])
        self.assertEqual(bodies(about="job"), ["Bring pole"])
        self.assertEqual(bodies(q="pole"), ["Bring pole"])


class DashboardLinksToFollowUpsTests(HubTestCase):
    def test_follow_up_card_opens_the_reps_own_follow_ups(self):
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, reverse("crm:task_followups") + "?mine=1")
