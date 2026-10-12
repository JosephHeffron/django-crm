"""Writing a business plan, and working through its checklist.

Phase 19 unit 2. The models, the list and the detail page have existed
since Phase 17; `plan_detail.html` carried the line "Editing plans and
ticking off steps arrives in Phase 19" and the Django admin was the
only way to create one. This is that.

Ticking is **one POST per step**, not a form over the whole checklist.
That is the owner's call and it is the right one: ticking one step
should not resubmit the other fourteen, and it works with no
JavaScript. The cost is a request per tick and a change-log entry per
tick, both asserted below.
"""

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import AuditLogEntry, BusinessPlan, PlanChecklistItem, Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"


def plan_for(owner, **extra):
    return BusinessPlan.objects.create(
        title=extra.pop("title", "Buy a second van"),
        owner=owner,
        created_by=owner,
        **extra,
    )


class PlanWritingTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("riley"), Role.SALES_REP)
        self.client.login(username="boss", password=PASSWORD)

    def post_plan(self, **extra):
        data = {
            "title": "Buy a second van",
            "description": "Price up a used Transit.",
            "owner": self.owner.pk,
            "due_date": "",
            "status": BusinessPlan.Status.NOT_STARTED,
            "priority": Task.Priority.MEDIUM,
        }
        data.update(extra)
        return self.client.post(reverse("crm:plan_create"), data)

    def test_a_plan_can_be_created_through_the_app(self):
        """The gap this unit closes: the admin was the only way in."""
        response = self.post_plan()
        self.assertIn(response.status_code, (301, 302))
        plan = BusinessPlan.objects.get(title="Buy a second van")
        self.assertEqual(plan.created_by, self.owner)
        self.assertEqual(plan.owner, self.owner)

    def test_the_form_offers_the_author_as_the_owner(self):
        """Most plans are your own, so the picker opens on you."""
        response = self.client.get(reverse("crm:plan_create"))
        self.assertEqual(response.context["form"].initial.get("owner"), self.owner.pk)

    def test_a_plan_cannot_be_assigned_to_a_crew_member(self):
        """It would sit on a page they cannot open: the Tasks hub is
        sales-and-owner, and `users/0004` gives cleaners no
        businessplan permissions at all."""
        casey = grant_role(f.user("casey"), Role.CLEANER)
        response = self.post_plan(owner=casey.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("owner", response.context["form"].errors)
        self.assertFalse(BusinessPlan.objects.exists())

    def test_a_plan_can_be_edited(self):
        plan = plan_for(self.owner)
        response = self.client.post(
            reverse("crm:plan_update", args=[plan.pk]),
            {
                "title": "Buy two more vans",
                "description": "",
                "owner": self.rep.pk,
                "due_date": (timezone.localdate() + timedelta(days=60)).isoformat(),
                "status": BusinessPlan.Status.IN_PROGRESS,
                "priority": Task.Priority.HIGH,
            },
        )
        self.assertIn(response.status_code, (301, 302))
        plan.refresh_from_db()
        self.assertEqual(plan.title, "Buy two more vans")
        self.assertEqual(plan.owner, self.rep)
        self.assertEqual(plan.status, BusinessPlan.Status.IN_PROGRESS)

    def test_an_empty_title_is_refused_rather_than_saved_blank(self):
        response = self.post_plan(title="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("title", response.context["form"].errors)
        self.assertFalse(BusinessPlan.objects.exists())

    def test_creating_and_editing_are_recorded_in_the_change_log(self):
        """Phase 18.5 unit 5 widened the log to everything the app
        writes, and `AuditedFormMixin` has to actually be reachable
        through this view's own `form_valid` — a mixin whose method is
        shadowed runs never and fails silently."""
        self.post_plan()
        plan = BusinessPlan.objects.get()
        entries = AuditLogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(BusinessPlan), object_id=plan.pk
        )
        self.assertEqual([e.action for e in entries], ["created"])

        self.client.post(
            reverse("crm:plan_update", args=[plan.pk]),
            {
                "title": "Buy a second van",
                "description": "Price up a used Transit.",
                "owner": self.owner.pk,
                "due_date": "",
                "status": BusinessPlan.Status.DONE,
                "priority": Task.Priority.MEDIUM,
            },
        )
        updated = entries.filter(action="updated").latest("pk")
        self.assertIn("status", updated.changes)

    def test_the_list_offers_a_way_in(self):
        """A form nothing links to is a form nobody finds."""
        response = self.client.get(reverse("crm:plan_list"))
        self.assertContains(response, reverse("crm:plan_create"))

    def test_the_detail_page_offers_an_edit_link(self):
        plan = plan_for(self.owner)
        response = self.client.get(plan.get_absolute_url())
        self.assertContains(response, reverse("crm:plan_update", args=[plan.pk]))


class ChecklistTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.client.login(username="boss", password=PASSWORD)
        self.plan = plan_for(self.owner)

    def add(self, text="Price up the van wrap"):
        return self.client.post(
            reverse("crm:plan_item_create", args=[self.plan.pk]), {"text": text}
        )

    def item(self, text="Step", is_done=False, position=1):
        return PlanChecklistItem.objects.create(
            plan=self.plan, text=text, is_done=is_done, position=position
        )

    def test_a_step_can_be_added(self):
        response = self.add()
        self.assertRedirects(response, self.plan.get_absolute_url())
        item = self.plan.items.get()
        self.assertEqual(item.text, "Price up the van wrap")
        self.assertFalse(item.is_done)

    def test_steps_keep_the_order_they_were_added_in(self):
        """A checklist is a sequence of thoughts; the order they
        arrived in is the useful one."""
        for text in ("First", "Second", "Third"):
            self.add(text)
        self.assertEqual([i.text for i in self.plan.items.all()], ["First", "Second", "Third"])

    def test_an_empty_step_is_refused_with_a_message(self):
        """Read from a followed response on purpose.

        `assertRedirects` fetches the redirect target to check it
        answers 200, and rendering that page consumes the message — so
        asserting on a *later* GET finds an empty list and reports a
        silent rejection that did not happen.
        """
        response = self.client.post(
            reverse("crm:plan_item_create", args=[self.plan.pk]), {"text": ""}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.plan.items.exists())
        said = " ".join(str(m) for m in response.context["messages"])
        self.assertTrue(said, "an empty step was rejected silently")

    def test_a_step_can_be_ticked_off(self):
        item = self.item()
        response = self.client.post(reverse("crm:plan_item_toggle", args=[item.pk]))
        self.assertRedirects(response, self.plan.get_absolute_url())
        item.refresh_from_db()
        self.assertTrue(item.is_done)

    def test_ticking_it_again_unticks_it(self):
        """A box you cannot untick is a box you are afraid to tick."""
        item = self.item(is_done=True)
        self.client.post(reverse("crm:plan_item_toggle", args=[item.pk]))
        item.refresh_from_db()
        self.assertFalse(item.is_done)

    def test_ticking_one_step_leaves_the_others_alone(self):
        """The whole reason this is a POST per step rather than one
        form over the checklist."""
        first, second, third = (self.item(f"Step {n}", position=n) for n in (1, 2, 3))
        self.client.post(reverse("crm:plan_item_toggle", args=[second.pk]))
        for item in (first, second, third):
            item.refresh_from_db()
        self.assertEqual([first.is_done, second.is_done, third.is_done], [False, True, False])

    def test_a_step_can_be_removed(self):
        """Without this a typo is permanent."""
        item = self.item("Pirce up the van wrap")
        response = self.client.post(reverse("crm:plan_item_remove", args=[item.pk]))
        self.assertRedirects(response, self.plan.get_absolute_url())
        self.assertFalse(self.plan.items.exists())

    def test_removing_a_step_leaves_the_plan_alone(self):
        item = self.item()
        self.client.post(reverse("crm:plan_item_remove", args=[item.pk]))
        self.assertTrue(BusinessPlan.objects.filter(pk=self.plan.pk).exists())

    def test_the_page_shows_progress_against_the_steps(self):
        self.item("Done one", is_done=True, position=1)
        self.item("Still to do", position=2)
        response = self.client.get(self.plan.get_absolute_url())
        self.assertEqual(response.context["done_count"], 1)
        self.assertEqual(len(response.context["items"]), 2)
        self.assertContains(response, "1 of 2 done")

    def test_every_step_gets_its_own_toggle_form(self):
        """Fifteen steps, fifteen endpoints — asserted because a single
        shared form would look identical on screen."""
        items = [self.item(f"Step {n}", position=n) for n in (1, 2, 3)]
        response = self.client.get(self.plan.get_absolute_url())
        for item in items:
            self.assertContains(response, reverse("crm:plan_item_toggle", args=[item.pk]))

    def test_the_controls_need_no_javascript(self):
        """They are ordinary forms, not a script's hooks."""
        self.item()
        body = self.client.get(self.plan.get_absolute_url()).content.decode()
        self.assertIn('<form method="post"', body)
        self.assertIn("csrfmiddlewaretoken", body)

    def test_a_tick_is_recorded_in_the_change_log(self):
        """Consistent with `JobStatusView`, which records a POST-only
        status change for the same reason."""
        item = self.item()
        self.client.post(reverse("crm:plan_item_toggle", args=[item.pk]))
        entry = AuditLogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(PlanChecklistItem)
        ).latest("pk")
        self.assertEqual(entry.action, "updated")
        self.assertIn("is_done", entry.changes)

    def test_a_logged_step_links_somewhere_real(self):
        """The change log renders `record.get_absolute_url` for every
        entry. A step has no page of its own, and Django resolves a
        missing template attribute to the empty string **silently**, so
        without `get_absolute_url` this would be a broken link rather
        than an error — invisible until somebody clicked it.
        """
        item = self.item()
        self.assertEqual(item.get_absolute_url(), self.plan.get_absolute_url())
        self.client.post(reverse("crm:plan_item_toggle", args=[item.pk]))
        response = self.client.get(reverse("core:activity_log"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.plan.get_absolute_url())

    def test_a_tick_cannot_be_undone_from_the_change_log(self):
        """`undo.UNDOABLE_MODELS` is an allow-list and does not name
        this model, so the entry is history rather than something with
        an Undo button — the discipline Phase 18.5 unit 5 established."""
        from apps.crm import undo

        self.assertNotIn(("crm", "planchecklistitem"), undo.UNDOABLE_MODELS)
        self.assertNotIn(("crm", "businessplan"), undo.UNDOABLE_MODELS)


class AccessTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("riley"), Role.SALES_REP)
        self.casey = grant_role(f.user("casey"), Role.CLEANER)
        self.plan = plan_for(self.owner)
        self.item = PlanChecklistItem.objects.create(plan=self.plan, text="Step", position=1)

    def test_a_sales_rep_can_write_a_plan_and_work_its_checklist(self):
        """`users/0004` gives them add/change on plans and full control
        of steps — removing a step off your own list is not the same as
        discarding the plan."""
        self.client.login(username="riley", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("crm:plan_create")).status_code, 200)
        self.assertIn(
            self.client.post(reverse("crm:plan_item_toggle", args=[self.item.pk])).status_code,
            (301, 302),
        )

    def test_a_crew_member_is_refused_everywhere(self):
        self.client.login(username="casey", password=PASSWORD)
        for method, url in (
            ("get", reverse("crm:plan_list")),
            ("get", reverse("crm:plan_create")),
            ("get", reverse("crm:plan_update", args=[self.plan.pk])),
            ("post", reverse("crm:plan_item_create", args=[self.plan.pk])),
            ("post", reverse("crm:plan_item_toggle", args=[self.item.pk])),
            ("post", reverse("crm:plan_item_remove", args=[self.item.pk])),
        ):
            self.assertEqual(getattr(self.client, method)(url).status_code, 403, url)
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_done)

    def test_a_signed_out_visitor_is_sent_to_sign_in(self):
        for url in (
            reverse("crm:plan_create"),
            reverse("crm:plan_update", args=[self.plan.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_the_write_endpoints_do_nothing_on_a_get(self):
        self.client.login(username="boss", password=PASSWORD)
        for url in (
            reverse("crm:plan_item_create", args=[self.plan.pk]),
            reverse("crm:plan_item_toggle", args=[self.item.pk]),
            reverse("crm:plan_item_remove", args=[self.item.pk]),
        ):
            self.assertIn(self.client.get(url).status_code, (403, 405), url)
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_done)
        self.assertEqual(self.plan.items.count(), 1)
