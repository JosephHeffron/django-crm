"""The Owner making and recovering accounts (ADR 0021).

There is no password-reset email on this system, so these two pages
*are* the recovery path: if they break, a locked-out employee needs a
superuser and a shell. Every test here is about something that would
leave somebody unable to work, or let somebody reach what they
shouldn't.
"""

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import resolve, reverse

from apps.crm.models import AuditLogEntry
from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.users.forms import RESERVED_USERNAMES
from apps.users.models import UserProfile, get_profile
from apps.users.roles import Role, user_role

User = get_user_model()

PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "a-different-long-password"
ADD = reverse("people:member_create")


class AddingSomebodyTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.client.force_login(self.owner)

    def post(self, **overrides):
        data = {
            "username": "newhire",
            "first_name": "Sam",
            "last_name": "Fielder",
            "email": "sam@example.test",
            "role": Role.CLEANER.value,
            "password1": NEW_PASSWORD,
            "password2": NEW_PASSWORD,
        }
        data.update(overrides)
        return self.client.post(ADD, data)

    def test_the_team_page_offers_it(self):
        """An account-creation page nobody can find leaves the owner
        back in the shell."""
        self.assertContains(self.client.get(reverse("people:team")), ADD)

    def test_the_new_person_can_sign_in_with_the_role_they_were_given(self):
        self.post()
        person = User.objects.get(username="newhire")
        self.assertEqual(user_role(person), Role.CLEANER)
        self.assertEqual((person.first_name, person.email), ("Sam", "sam@example.test"))
        self.assertTrue(self.client.login(username="newhire", password=NEW_PASSWORD))

    def test_no_role_means_no_role_not_an_error(self):
        """Somebody can exist before you decide what they do."""
        self.post(username="undecided", role="")
        self.assertIsNone(user_role(User.objects.get(username="undecided")))

    def test_a_weak_password_is_refused(self):
        """The owner typing the password must not sidestep the rules a
        person changing their own is held to — this project raised the
        minimum to 12 characters (AUTH_PASSWORD_VALIDATORS)."""
        response = self.post(password1="short1", password2="short1")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newhire").exists())

    def test_a_mistyped_confirmation_is_refused(self):
        response = self.post(password2=NEW_PASSWORD + "-oops")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newhire").exists())

    def test_a_taken_username_is_refused(self):
        response = self.post(username="boss")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="boss").count(), 1)

    def test_the_account_and_the_role_arrive_together_or_not_at_all(self):
        """Django's creation form commits the user before returning, so
        a failure while assigning the group would leave the username
        taken, the person role-less, and the owner unable to retry under
        the same name.
        """
        with mock.patch("apps.users.forms._set_role", side_effect=RuntimeError("no groups")):
            with self.assertRaises(RuntimeError):
                self.post(username="halfway")
        self.assertFalse(User.objects.filter(username="halfway").exists())

    def test_a_username_differing_only_in_case_is_refused(self):
        """Django's UserCreationForm is the whole of this check — the
        username column is exact-match, so without it "boss" and "Boss"
        would both exist, and which one a sign-in reached would depend
        on exactly what was typed.
        """
        response = self.post(username="Boss")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username__iexact="boss").count(), 1)

    def test_a_name_a_page_already_answers_to_is_refused(self):
        for name in sorted(RESERVED_USERNAMES):
            response = self.post(username=name)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(User.objects.filter(username=name).exists(), name)

    def test_a_reserved_name_is_one_the_routes_would_swallow(self):
        """Keeps the reservation list honest. Each entry has to be a
        name whose member page really does resolve elsewhere — so the
        list cannot grow by habit, and a route rename makes this fail
        instead of leaving a needless restriction behind.
        """
        for name in sorted(RESERVED_USERNAMES):
            self.assertEqual(
                resolve(reverse("people:member", args=[name])).view_name,
                "people:member_create",
                f"{name} is reserved but its page resolves to itself",
            )

    def test_only_the_owner_can_add_anybody(self):
        for user, expected in (
            (grant_role(f.user("rep"), Role.SALES_REP), 403),
            (grant_role(f.user("crew"), Role.CLEANER), 403),
            (f.user("nobody"), 403),
        ):
            self.client.force_login(user)
            self.assertEqual(self.client.get(ADD).status_code, expected)
            self.assertEqual(self.post(username=f"by-{user.username}").status_code, expected)
            self.assertFalse(User.objects.filter(username=f"by-{user.username}").exists())

    def test_signed_out_is_sent_to_the_sign_in_page(self):
        self.client.logout()
        response = self.client.get(ADD)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response["Location"])


class WhatTheLogRecordsTests(TestCase):
    """Account administration appears in the change log (owner's ask,
    2026-11-03).

    Nothing notifies the person — there is no email on this system — so
    the log is the only record that somebody's access or password was
    changed, and by whom. What it must **not** hold is anything that
    would let a reader sign in as them.
    """

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.crew = grant_role(f.user("crew"), Role.CLEANER)
        self.client.force_login(self.owner)

    def entries(self):
        return AuditLogEntry.objects.order_by("pk")

    def test_setting_a_password_is_recorded_against_the_person(self):
        self.client.post(
            reverse("people:member", args=["crew"]),
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        entry = self.entries().get()
        self.assertEqual(entry.user, self.owner)
        self.assertEqual(entry.record, self.crew)
        self.assertEqual(entry.action, AuditLogEntry.Action.UPDATED)
        self.assertEqual(entry.changes, {"password": [None, "changed"]})

    def test_the_entry_carries_no_password_and_no_hash(self):
        """The log is Owner-only, but it is still a page: an entry that
        quoted the password, or the hash it was stored as, would turn
        reading the log into a way to sign in as somebody.
        """
        self.client.post(
            reverse("people:member", args=["crew"]),
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.crew.refresh_from_db()
        written = json.dumps(self.entries().get().changes)
        self.assertNotIn(NEW_PASSWORD, written)
        self.assertNotIn(self.crew.password, written)
        self.assertNotIn("pbkdf2", written)

    def test_a_refused_password_records_nothing(self):
        """Too short to be accepted, so nothing happened, so there is
        nothing to record."""
        self.client.post(
            reverse("people:member", args=["crew"]),
            {"new_password1": "short1", "new_password2": "short1"},
        )
        self.assertEqual(self.entries().count(), 0)

    def test_adding_somebody_is_recorded(self):
        self.client.post(
            ADD,
            {
                "username": "newhire",
                "first_name": "Sam",
                "last_name": "Fielder",
                "email": "sam@example.test",
                "role": Role.CLEANER.value,
                "password1": NEW_PASSWORD,
                "password2": NEW_PASSWORD,
            },
        )
        entry = self.entries().get()
        self.assertEqual(entry.action, AuditLogEntry.Action.CREATED)
        self.assertEqual(entry.record, User.objects.get(username="newhire"))
        self.assertEqual(entry.user, self.owner)

    def test_a_role_change_and_a_deactivation_are_recorded(self):
        """A demotion that left no trace, on a page whose password
        change does, would be an odd place to stop."""
        self.client.post(
            reverse("people:member", args=["crew"]),
            {"role": Role.SALES_REP.value, "is_active": "on"},
        )
        self.assertEqual(self.entries().get().changes, {"role": ["Cleaner", "Sales Rep"]})

        self.client.post(reverse("people:member", args=["crew"]), {"role": Role.SALES_REP.value})
        self.assertEqual(self.entries().last().changes, {"is_active": ["yes", "no"]})

    def test_turning_sign_in_off_reads_as_no_not_a_dash(self):
        """The change-log template runs every value through `default`,
        and `False` is falsy — so storing the boolean showed the owner
        `is_active: True → —`, which says nothing.
        """
        self.client.post(reverse("people:member", args=["crew"]), {"role": Role.CLEANER.value})
        page = self.client.get(reverse("core:activity_log"))
        # The rendered pair, not a bare "no" that could come from
        # anywhere else on the page.
        self.assertContains(page, '<span class="muted">yes</span> \u2192 no', html=False)

    def test_a_superusers_role_change_is_recorded(self):
        """`user_role()` answers Owner for any superuser, whatever
        groups they hold, so comparing effective roles would call this
        no change while the saved group really moved.
        """
        admin = grant_role(f.user("admin", is_superuser=True), Role.CLEANER)
        self.client.post(
            reverse("people:member", args=["admin"]),
            {"role": Role.SALES_REP.value, "is_active": "on"},
        )
        self.assertEqual(self.entries().get().changes, {"role": ["Cleaner", "Sales Rep"]})
        self.assertEqual(set(admin.groups.values_list("name", flat=True)), {Role.SALES_REP.value})

    def test_a_failed_entry_takes_the_password_change_with_it(self):
        """The log is the only record that a password changed, so a
        change that could not be recorded must not stand.
        """
        with mock.patch("apps.users.views.record", side_effect=RuntimeError("no log")):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("people:member", args=["crew"]),
                    {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
                )
        self.assertEqual(self.entries().count(), 0)
        self.assertTrue(self.client_class().login(username="crew", password=PASSWORD))

    def test_saving_the_same_access_again_records_nothing(self):
        """A log whose job is to be readable should not fill with
        entries saying nothing moved."""
        same = {"role": Role.CLEANER.value, "is_active": "on"}
        self.client.post(reverse("people:member", args=["crew"]), same)
        self.assertEqual(self.entries().count(), 0)

    def test_a_pay_change_is_recorded_readably(self):
        """The hourly rate is money, so a change to it belongs in the
        log for the same reason a role change does. Stored as the words
        the page shows: "01" would be a true record of the column and
        useless to a reader.
        """
        self.client.post(
            reverse("people:member", args=["crew"]),
            {"hourly_rate": "24.50", "working_days": ["0", "1"]},
        )
        entry = self.entries().get()
        self.assertEqual(entry.record, self.crew)
        self.assertEqual(
            entry.changes,
            {
                "hourly_rate": ["", "24.50"],
                "working_days": ["varies", "Mon, Tue"],
            },
        )

    def test_saving_the_same_pay_again_records_nothing(self):
        same = {"hourly_rate": "24.50", "working_days": ["0", "1"]}
        self.client.post(reverse("people:member", args=["crew"]), same)
        self.client.post(reverse("people:member", args=["crew"]), same)
        self.assertEqual(self.entries().count(), 1)

    def test_saving_pay_does_not_revert_a_concurrent_profile_edit(self):
        """The hazard: the pay form holds the profile row as it was when
        the owner opened the page, so a full save writes every column
        back — reverting whatever the person changed about themselves in
        between.

        Simulated by writing the phone directly while the request is
        mid-flight: `_pay_state` runs inside the same transaction,
        immediately after the row is locked and before the pay fields
        are written, so a side effect there lands in exactly the window
        a real concurrent edit would.
        """
        import apps.users.views as views

        real_state = views._pay_state
        # Once, on the first call only. Firing on both calls wrote the
        # phone again *after* the save, so the harness repaired the very
        # clobbering it was meant to catch and the test passed against
        # the bug.
        edited_yet = []

        def edit_their_profile(profile):
            if not edited_yet:
                edited_yet.append(True)
                UserProfile.objects.filter(pk=profile.pk).update(phone="555-0000")
            return real_state(profile)

        with mock.patch.object(views, "_pay_state", side_effect=edit_their_profile):
            self.client.post(
                reverse("people:member", args=["crew"]),
                {"hourly_rate": "31.00", "working_days": ["2"]},
            )

        profile = get_profile(self.crew)
        self.assertEqual(profile.phone, "555-0000", "their own edit was reverted")
        self.assertEqual(str(profile.hourly_rate), "31.00")
        self.assertEqual(profile.working_days_display, "Wed")

    def test_a_failed_entry_takes_the_pay_change_with_it(self):
        with mock.patch("apps.users.views.record", side_effect=RuntimeError("no log")):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("people:member", args=["crew"]),
                    {"hourly_rate": "99.00", "working_days": []},
                )
        self.assertIsNone(get_profile(self.crew).hourly_rate)

    def test_the_change_log_page_links_to_the_person(self):
        """auth.User has no get_absolute_url, and the template's
        fallback renders a missing attribute as an empty string — so
        without the view naming this URL the entry had a link that went
        nowhere.
        """
        self.client.post(
            reverse("people:member", args=["crew"]),
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        page = self.client.get(reverse("core:activity_log"))
        self.assertContains(page, reverse("people:member", args=["crew"]))
        self.assertNotContains(page, 'href=""')

    def test_only_the_owner_can_read_it(self):
        """The log now names who changed whose access. That is not for
        everybody."""
        for user in (grant_role(f.user("rep"), Role.SALES_REP), f.user("nobody")):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("core:activity_log")).status_code, 403)


class SettingSomebodysPasswordTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.crew = grant_role(f.user("crew"), Role.CLEANER)
        self.page = reverse("people:member", args=["crew"])
        self.client.force_login(self.owner)

    def post(self, **overrides):
        data = {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        data.update(overrides)
        return self.client.post(self.page, data)

    def test_the_page_offers_it(self):
        self.assertContains(self.client.get(self.page), "Set a new password")

    def test_the_new_password_works_and_the_old_one_stops(self):
        self.post()
        signing_in = self.client_class()
        self.assertTrue(signing_in.login(username="crew", password=NEW_PASSWORD))
        self.assertFalse(signing_in.login(username="crew", password=PASSWORD))

    def test_it_signs_that_person_out_everywhere(self):
        """The reason to reset a password is often that somebody else
        has it. A reset that left their open sessions working would not
        shut that person out.
        """
        theirs = self.client_class()
        theirs.force_login(self.crew)
        self.assertEqual(theirs.get(reverse("people:profile")).status_code, 200)
        self.post()
        after = theirs.get(reverse("people:profile"))
        self.assertEqual(after.status_code, 302)
        self.assertIn(reverse("users:login"), after["Location"])

    def test_a_weak_password_is_refused_and_theirs_still_works(self):
        response = self.post(new_password1="short1", new_password2="short1")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client_class().login(username="crew", password=PASSWORD))

    def test_a_mistyped_confirmation_is_refused(self):
        response = self.post(new_password2=NEW_PASSWORD + "-oops")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client_class().login(username="crew", password=PASSWORD))

    def test_setting_a_password_leaves_role_and_sign_in_alone(self):
        """Three forms post to this one page. Posting one must not save
        another's fields — a set-password that also cleared somebody's
        role would be a quiet demotion.
        """
        self.post()
        self.crew.refresh_from_db()
        self.assertEqual(user_role(self.crew), Role.CLEANER)
        self.assertTrue(self.crew.is_active)

    def test_one_owner_can_reset_another_owner(self):
        """The documented recovery path for a locked-out owner
        (docs/ADMIN_GUIDE.md, ADR 0021): with two Owner accounts, either
        can reset the other entirely in the app, so losing a password
        does not need server access. The refusal is only ever about
        acting on *yourself*.
        """
        other_owner = grant_role(f.user("co-boss"), Role.OWNER)
        response = self.client.post(
            reverse("people:member", args=["co-boss"]),
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.assertRedirects(response, reverse("people:member", args=["co-boss"]))
        self.assertTrue(self.client_class().login(username="co-boss", password=NEW_PASSWORD))
        self.assertEqual(user_role(other_owner), Role.OWNER)

    def test_the_owner_cannot_set_their_own_from_here(self):
        """Django asks for the old password when you change your own.
        This page doesn't, so it must not become a way around that for
        whoever is signed in.
        """
        response = self.client.post(
            reverse("people:member", args=["boss"]),
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.assertRedirects(response, reverse("users:password_change"))
        self.assertTrue(self.client_class().login(username="boss", password=PASSWORD))

    def test_nobody_else_can_set_anybodys_password(self):
        for user in (
            grant_role(f.user("rep"), Role.SALES_REP),
            grant_role(f.user("other-crew"), Role.CLEANER),
            f.user("nobody"),
        ):
            self.client.force_login(user)
            self.assertEqual(self.post().status_code, 403)
            self.assertTrue(
                self.client_class().login(username="crew", password=PASSWORD),
                f"{user.username} changed somebody else's password",
            )
