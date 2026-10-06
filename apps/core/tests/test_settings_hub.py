from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core import changelog
from apps.crm import undo
from apps.crm.models import AuditLogEntry, Company, Contact
from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.users.roles import Role, user_role

PASSWORD = "correct-horse-battery"
HUB = reverse("core:settings")
LOG = reverse("core:activity_log")
CUSTOMIZE = reverse("core:customize")
WHATS_NEW = reverse("core:whats_new")


class HubTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.client.login(username="boss", password=PASSWORD)

    def titles(self):
        return {card["title"] for card in self.client.get(HUB).context["cards"]}

    def test_the_owner_sees_everything(self):
        shown = self.titles()
        for title in ("Business settings", "Company management", "Activity log", "Customize"):
            self.assertIn(title, shown)

    def test_a_rep_sees_only_what_they_can_open(self):
        grant_role(f.user("rep"), Role.SALES_REP)
        self.client.login(username="rep", password=PASSWORD)
        shown = self.titles()
        self.assertIn("Account settings", shown)
        self.assertIn("What's new", shown)
        self.assertNotIn("Business settings", shown)
        self.assertNotIn("Activity log", shown)

    def test_every_card_opens_for_whoever_is_shown_it(self):
        people = (("boss2", Role.OWNER), ("rep2", Role.SALES_REP), ("crew", Role.CLEANER))
        for username, role in people:
            grant_role(f.user(username), role)
            self.client.login(username=username, password=PASSWORD)
            for card in self.client.get(HUB).context["cards"]:
                self.assertEqual(self.client.get(card["url"]).status_code, 200, card["url"])

    def test_someone_with_no_role_gets_no_hub(self):
        # Every page it links to needs a role, so the hub does too.
        f.user("nobody")
        self.client.login(username="nobody", password=PASSWORD)
        self.assertEqual(self.client.get(HUB).status_code, 403)


class CustomizeTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.client.login(username="boss", password=PASSWORD)

    def test_it_lists_the_services(self):
        response = self.client.get(CUSTOMIZE)
        self.assertContains(response, f.service().name)
        self.assertGreater(response.context["active_services"], 0)

    def test_only_the_owner(self):
        grant_role(f.user("rep"), Role.SALES_REP)
        self.client.login(username="rep", password=PASSWORD)
        self.assertEqual(self.client.get(CUSTOMIZE).status_code, 403)


class WhatsNewTests(TestCase):
    def setUp(self):
        grant_role(f.user("rep"), Role.SALES_REP)
        self.client.login(username="rep", password=PASSWORD)

    def test_it_reads_the_changelog(self):
        response = self.client.get(WHATS_NEW)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["releases"])

    def test_the_parser_reads_keep_a_changelog_shape(self):
        releases = changelog._parse(
            "# Changelog\n\n"
            "## [1.2.0] - 2026-10-01\n\n"
            "### Added\n- A thing\n- Another thing\n\n"
            "### Fixed\n- A bug\n\n"
            "## [1.1.0] - 2026-09-01\n\n"
            "### Added\n- Something older\n"
        )
        self.assertEqual([r["version"] for r in releases], ["1.2.0", "1.1.0"])
        self.assertEqual(releases[0]["date"], "2026-10-01")
        self.assertEqual([g["name"] for g in releases[0]["groups"]], ["Added", "Fixed"])
        self.assertEqual(releases[0]["groups"][0]["entries"], ["A thing", "Another thing"])

    def test_a_release_with_nothing_under_it_is_skipped(self):
        releases = changelog._parse("## [0.1.0] - 2026-01-01\n\nJust prose, no list.\n")
        self.assertEqual(releases, [])

    def test_a_wrapped_note_keeps_its_second_line(self):
        releases = changelog._parse(
            "## [1.0] - 2026-01-01\n\n### Added\n"
            "- A note long enough that it wraps\n  onto a second line\n"
            "- A short one\n"
        )
        self.assertEqual(
            releases[0]["groups"][0]["entries"],
            ["A note long enough that it wraps onto a second line", "A short one"],
        )

    def test_a_missing_file_is_not_a_crash(self):
        with self.settings(BASE_DIR="/nowhere/at/all"):
            self.assertEqual(changelog.releases(), [])


class ActivityLogTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.client.login(username="boss", password=PASSWORD)
        self.contact = f.contact(self.owner, "Pat", "Homeowner", email="pat@example.com")

    def edit(self, **changes):
        """Record an edit the way the contact form does."""
        entry = AuditLogEntry.objects.create(
            content_type=ContentType.objects.get_for_model(self.contact),
            object_id=self.contact.pk,
            user=self.owner,
            action=AuditLogEntry.Action.UPDATED,
            changes=changes,
        )
        return entry

    def test_only_the_owner_reads_the_log(self):
        grant_role(f.user("rep"), Role.SALES_REP)
        self.client.login(username="rep", password=PASSWORD)
        self.assertEqual(self.client.get(LOG).status_code, 403)

    def test_it_lists_what_changed(self):
        self.edit(first_name=["Pat", "Patricia"])
        response = self.client.get(LOG)
        self.assertContains(response, "first_name")
        self.assertContains(response, "Patricia")

    def test_undoing_an_edit_puts_it_back_and_records_that_it_did(self):
        Contact.objects.filter(pk=self.contact.pk).update(first_name="Patricia")
        entry = self.edit(first_name=["Pat", "Patricia"])
        response = self.client.post(reverse("core:activity_undo", args=[entry.pk]), follow=True)
        self.assertContains(response, "Put back first_name")
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.first_name, "Pat")
        # The undo is itself in the log, so the record tells the whole story.
        latest = AuditLogEntry.objects.order_by("-pk").first()
        self.assertEqual(latest.changes, {"first_name": ["Patricia", "Pat"]})

    def test_an_edit_somebody_has_changed_since_is_refused(self):
        entry = self.edit(first_name=["Pat", "Patricia"])
        Contact.objects.filter(pk=self.contact.pk).update(first_name="Trish")
        response = self.client.post(reverse("core:activity_undo", args=[entry.pk]), follow=True)
        self.assertContains(response, "has changed")
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.first_name, "Trish")

    def test_a_creation_cannot_be_undone(self):
        entry = AuditLogEntry.objects.create(
            content_type=ContentType.objects.get_for_model(self.contact),
            object_id=self.contact.pk,
            user=self.owner,
            action=AuditLogEntry.Action.CREATED,
        )
        self.assertIn("Only edits", undo.why_not(entry))
        response = self.client.post(reverse("core:activity_undo", args=[entry.pk]), follow=True)
        self.assertContains(response, "Only edits")

    def test_a_field_that_cannot_be_put_back_exactly_says_so(self):
        # The log stores text; "Oct 5, 2026" doesn't identify a date and
        # a person's name doesn't identify a row.
        entry = self.edit(owner=["Olivia Grant", "Robin Reyes"])
        self.assertIsNotNone(undo.why_not(entry))
        self.assertIn("put back automatically", undo.why_not(entry))
        self.assertContains(self.client.get(LOG), "put back automatically")

    def test_a_record_that_is_gone_cannot_be_undone(self):
        entry = self.edit(first_name=["Pat", "Patricia"])
        self.contact.delete()
        entry.refresh_from_db()
        self.assertIn("gone", undo.why_not(entry))

    def test_undo_restores_several_fields_at_once(self):
        Contact.objects.filter(pk=self.contact.pk).update(first_name="Patricia", phone="555-0199")
        entry = self.edit(first_name=["Pat", "Patricia"], phone=["", "555-0199"])
        self.client.post(reverse("core:activity_undo", args=[entry.pk]))
        self.contact.refresh_from_db()
        self.assertEqual((self.contact.first_name, self.contact.phone), ("Pat", ""))


class UndoSafetyTests(TestCase):
    """The parts of undo that exist to stop it losing work."""

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.client.login(username="boss", password=PASSWORD)
        self.contact = f.contact(self.owner, "Pat", "Homeowner")

    def entry(self, **changes):
        return AuditLogEntry.objects.create(
            content_type=ContentType.objects.get_for_model(self.contact),
            object_id=self.contact.pk,
            user=self.owner,
            action=AuditLogEntry.Action.UPDATED,
            changes=changes,
        )

    def test_a_field_that_decides_what_else_exists_is_refused(self):
        # Putting "customer" back to "lead" would say the conversion
        # never happened while everything it created still exists.
        entry = self.entry(status=["lead", "customer"])
        self.assertIn("decides what else exists", undo.why_not(entry))

    def test_undo_touches_the_updated_time(self):
        Contact.objects.filter(pk=self.contact.pk).update(first_name="Patricia")
        self.contact.refresh_from_db()
        before = self.contact.updated_at
        entry = self.entry(first_name=["Pat", "Patricia"])
        undo.undo(entry, self.owner)
        self.contact.refresh_from_db()
        self.assertGreater(self.contact.updated_at, before)

    def test_undo_reads_the_record_inside_its_own_transaction(self):
        # The check and the write have to see the same row, or an edit
        # landing between them is overwritten.
        Contact.objects.filter(pk=self.contact.pk).update(first_name="Patricia")
        entry = self.entry(first_name=["Pat", "Patricia"])
        with CaptureQueriesContext(connection) as captured:
            undo.undo(entry, self.owner)
        self.assertTrue(
            any("FOR UPDATE" in query["sql"].upper() for query in captured),
            "the row should be locked while it's checked and written",
        )

    def test_the_log_does_not_fetch_a_record_per_row(self):
        for index in range(6):
            self.entry(**{"first_name": [f"Old {index}", "Pat"]})
        with CaptureQueriesContext(connection) as few:
            self.client.get(LOG)
        for index in range(12):
            self.entry(**{"last_name": [f"Old {index}", "Homeowner"]})
        with CaptureQueriesContext(connection) as many:
            self.client.get(LOG)
        self.assertEqual(len(few), len(many))


class MemberAccessTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("rep", first_name="Robin"), Role.SALES_REP)
        self.client.login(username="boss", password=PASSWORD)
        self.url = reverse("people:member", args=["rep"])

    def test_the_owner_changes_what_someone_can_reach(self):
        response = self.client.post(self.url, {"role": Role.CLEANER.value, "is_active": "on"})
        self.assertRedirects(response, self.url)
        self.rep.refresh_from_db()
        self.assertEqual(user_role(self.rep), Role.CLEANER)

    def test_changing_a_role_leaves_only_one(self):
        self.client.post(self.url, {"role": Role.OWNER.value, "is_active": "on"})
        names = set(self.rep.groups.values_list("name", flat=True))
        self.assertEqual(names & {r.value for r in Role}, {Role.OWNER.value})

    def test_taking_the_role_away_leaves_them_signed_in_but_empty_handed(self):
        self.client.post(self.url, {"role": "", "is_active": "on"})
        self.rep.refresh_from_db()
        self.assertIsNone(user_role(self.rep))
        self.assertTrue(self.rep.is_active)

    def test_turning_off_sign_in_keeps_their_records(self):
        company = Company.objects.create(name="Acme", created_by=self.rep)
        self.client.post(self.url, {"role": Role.SALES_REP.value})
        self.rep.refresh_from_db()
        self.assertFalse(self.rep.is_active)
        self.assertTrue(Company.objects.filter(pk=company.pk).exists())

    def test_nobody_else_can_change_access(self):
        grant_role(f.user("other"), Role.SALES_REP)
        self.client.login(username="other", password=PASSWORD)
        response = self.client.post(self.url, {"role": Role.OWNER.value, "is_active": "on"})
        self.assertEqual(response.status_code, 403)
        self.rep.refresh_from_db()
        self.assertEqual(user_role(self.rep), Role.SALES_REP)

    def test_somebody_whose_sign_in_is_off_is_still_reachable(self):
        # Otherwise turning it off is a one-way door: they vanish from
        # the only page that can turn it back on.
        self.client.post(self.url, {"role": Role.SALES_REP.value})
        self.rep.refresh_from_db()
        self.assertFalse(self.rep.is_active)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertContains(self.client.get(reverse("people:team")), "rep")

    def test_sign_in_can_be_turned_back_on(self):
        self.client.post(self.url, {"role": Role.SALES_REP.value})
        self.client.post(self.url, {"role": Role.SALES_REP.value, "is_active": "on"})
        self.rep.refresh_from_db()
        self.assertTrue(self.rep.is_active)

    def test_an_owner_cannot_take_away_their_own_access(self):
        own = reverse("people:member", args=["boss"])
        response = self.client.post(own, {"role": "", "is_active": "on"}, follow=True)
        self.assertContains(response, "change your own access")  # the apostrophe is escaped
        self.owner.refresh_from_db()
        self.assertEqual(user_role(self.owner), Role.OWNER)

    def test_the_roles_offered_are_the_ones_the_app_knows(self):
        response = self.client.get(self.url)
        choices = dict(response.context["access_form"].fields["role"].choices)
        self.assertEqual(set(choices) - {""}, {role.value for role in Role})
        self.assertTrue(Group.objects.filter(name__in=choices.keys()).exists())
