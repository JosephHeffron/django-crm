"""Spotting a customer who is already on the books (Phase 22).

The rule these tests exist to hold: this **warns and never blocks.**
Two people can share a name and a couple can share a phone number, so
a check that refused the second record would be worse than the
occasional duplicate. Every test here that asserts a warning also
asserts the save goes through once confirmed.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.crm import duplicates
from apps.crm.models import Contact
from apps.crm.tests._helpers import grant_role

User = get_user_model()

PASSWORD = "correct-horse-battery"
CREATE = reverse("crm:contact_create")


class PhoneDigitsTests(TestCase):
    def test_the_same_number_written_four_ways_is_one_number(self):
        written = ("585-555-0100", "(585) 555-0100", "5855550100", "+1 585 555 0100")
        self.assertEqual({duplicates.digits(p) for p in written}, {"5855550100"})

    def test_nothing_in_means_nothing_out(self):
        self.assertEqual(duplicates.digits(""), "")
        self.assertEqual(duplicates.digits(None), "")
        self.assertEqual(duplicates.digits("no digits here"), "")


class FindingThemTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("boss", password=PASSWORD)
        grant_role(self.user)
        self.pat = Contact.objects.create(
            first_name="Pat",
            last_name="Homeowner",
            email="pat@example.test",
            phone="585-555-0100",
            created_by=self.user,
        )

    def test_the_same_name_is_a_match(self):
        found = duplicates.likely_duplicates(first_name="pat", last_name="HOMEOWNER")
        self.assertEqual([c.pk for c in found], [self.pat.pk])

    def test_a_shared_surname_alone_is_not(self):
        """A book of business has several Smiths. Matching on one name
        would warn on half of them and teach people to click through
        the warning without reading it."""
        self.assertEqual(list(duplicates.likely_duplicates(last_name="Homeowner")), [])
        self.assertEqual(list(duplicates.likely_duplicates(first_name="Pat")), [])

    def test_the_same_email_is_a_match_whatever_the_name(self):
        found = duplicates.likely_duplicates(
            first_name="Patricia", last_name="Different", email="PAT@example.test"
        )
        self.assertEqual([c.pk for c in found], [self.pat.pk])

    def test_the_same_phone_written_differently_is_a_match(self):
        found = duplicates.likely_duplicates(
            first_name="Someone", last_name="Else", phone="(585) 555-0100"
        )
        self.assertEqual([c.pk for c in found], [self.pat.pk])

    def test_a_different_phone_is_not(self):
        found = duplicates.likely_duplicates(
            first_name="Someone", last_name="Else", phone="585-555-9999"
        )
        self.assertEqual(list(found), [])

    def test_an_empty_form_matches_nobody(self):
        """Not everybody — the obvious wrong answer, since an empty Q
        combined with OR would match the whole table."""
        self.assertEqual(list(duplicates.likely_duplicates()), [])

    def test_a_deactivated_customer_still_counts(self):
        """ "You deactivated them last year" is exactly what somebody
        re-adding them needs to hear."""
        self.pat.is_active = False
        self.pat.save(update_fields=["is_active"])
        found = duplicates.likely_duplicates(first_name="Pat", last_name="Homeowner")
        self.assertEqual([c.pk for c in found], [self.pat.pk])

    def test_the_contact_being_edited_can_be_excluded(self):
        found = duplicates.likely_duplicates(
            first_name="Pat", last_name="Homeowner", exclude_pk=self.pat.pk
        )
        self.assertEqual(list(found), [])

    def test_it_says_which_of_the_three_matched(self):
        why = duplicates.reasons(
            self.pat, first_name="Pat", last_name="Homeowner", phone="5855550100"
        )
        self.assertEqual(why, ["the same name", "the same phone number"])
        self.assertEqual(duplicates.reasons(self.pat, email="pat@example.test"), ["the same email"])


class AddingThemAnywayTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("boss", password=PASSWORD)
        grant_role(self.user)
        self.client.login(username="boss", password=PASSWORD)
        self.pat = Contact.objects.create(
            first_name="Pat",
            last_name="Homeowner",
            email="pat@example.test",
            phone="585-555-0100",
            created_by=self.user,
        )

    def form(self, **extra):
        data = {
            "first_name": "Pat",
            "last_name": "Homeowner",
            "status": Contact.Status.CUSTOMER,
            "email": "",
            "phone": "",
            "notes": "",
        }
        data.update(extra)
        return data

    def test_the_first_attempt_asks_rather_than_saving(self):
        response = self.client.post(CREATE, self.form())
        self.assertEqual(response.status_code, 200, "re-rendered, not redirected")
        self.assertEqual(Contact.objects.filter(last_name="Homeowner").count(), 1)
        self.assertContains(response, "Already on the books?")
        self.assertContains(response, "the same name")
        self.assertContains(response, self.pat.get_absolute_url())

    def test_ticking_the_box_saves_the_second_person(self):
        """The half that matters. A check that cannot be overridden
        would stop a business adding a real second customer with the
        same name."""
        self.client.post(CREATE, self.form(confirm_duplicate="on"))
        self.assertEqual(Contact.objects.filter(last_name="Homeowner").count(), 2)

    def test_somebody_new_is_saved_first_time(self):
        self.client.post(CREATE, self.form(first_name="Sam", last_name="Newman"))
        self.assertTrue(Contact.objects.filter(last_name="Newman").exists())

    def test_editing_an_existing_customer_is_never_blocked_by_itself(self):
        """`clean()` skips the check when editing. Without that, saving
        any customer unchanged would warn that they already exist."""
        response = self.client.post(
            reverse("crm:contact_update", args=[self.pat.pk]),
            self.form(email="pat@example.test", phone="585-555-0100"),
        )
        self.assertEqual(response.status_code, 302, "saved, not re-asked")
        self.assertNotContains(
            self.client.get(reverse("crm:contact_update", args=[self.pat.pk])),
            "Already on the books?",
        )
