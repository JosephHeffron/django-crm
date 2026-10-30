"""The Owner making and recovering accounts (ADR 0021).

There is no password-reset email on this system, so these two pages
*are* the recovery path: if they break, a locked-out employee needs a
superuser and a shell. Every test here is about something that would
leave somebody unable to work, or let somebody reach what they
shouldn't.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
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
