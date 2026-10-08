"""The address form the app never had, and the round trip to it.

Until this unit a service address could only be created through the
Django admin, which is why booking a job for a new customer meant
leaving the app.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.redirects import with_params
from apps.crm.models import Contact, Property
from apps.crm.tests._helpers import grant_role
from apps.users.roles import Role

User = get_user_model()
PASSWORD = "correct-horse-battery"
ADD = reverse("crm:property_create")


class PropertyTestCase(TestCase):
    def setUp(self):
        self.rep = grant_role(User.objects.create_user("rep", password=PASSWORD))
        self.customer = Contact.objects.create(
            first_name="Pat", last_name="Homeowner", created_by=self.rep
        )
        self.client.login(username="rep", password=PASSWORD)

    def fields(self, **extra):
        data = {
            "contact": self.customer.pk,
            "label": "Home",
            "street": "12 Oak Ave",
            "city": "Penfield",
            "state": "NY",
            "postal_code": "14526",
            "notes": "",
        }
        data.update(extra)
        return data

    def address(self, street="1 First St", primary=False, contact=None):
        return Property.objects.create(
            contact=contact or self.customer,
            street=street,
            city="Penfield",
            state="NY",
            postal_code="14526",
            is_primary=primary,
        )


class AddingAnAddressTests(PropertyTestCase):
    def test_an_address_can_be_added(self):
        self.client.post(ADD, self.fields())
        saved = Property.objects.get(street="12 Oak Ave")
        self.assertEqual((saved.contact_id, saved.city), (self.customer.pk, "Penfield"))

    def test_it_appears_on_the_customer(self):
        self.client.post(ADD, self.fields())
        page = self.client.get(self.customer.get_absolute_url())
        self.assertContains(page, "12 Oak Ave")

    def test_a_street_a_town_a_state_and_a_postcode_are_all_required(self):
        for missing in ("street", "city", "state", "postal_code"):
            response = self.client.post(ADD, self.fields(**{missing: ""}))
            self.assertEqual(response.status_code, 200, missing)
            self.assertIn(missing, response.context["form"].errors, missing)
        self.assertFalse(Property.objects.exists())

    def test_the_form_can_start_with_a_customer_chosen(self):
        form = self.client.get(ADD, {"contact": self.customer.pk}).context["form"]
        self.assertEqual(form.initial.get("contact"), self.customer.pk)

    def test_an_address_can_be_corrected(self):
        address = self.address()
        self.client.post(
            reverse("crm:property_update", args=[address.pk]),
            self.fields(street="2 Elm Rd"),
        )
        address.refresh_from_db()
        self.assertEqual(address.street, "2 Elm Rd")

    def test_a_corrected_address_is_asked_about_again(self):
        """Editing the street re-opens the map lookup by itself.

        `located_address` is a snapshot of what was placed, so changing
        the street makes the two disagree and `needing_location()`
        picks it up.
        """
        address = self.address()
        address.latitude, address.longitude = 43.1, -77.6
        address.located_address = str(address)
        address.save()
        self.assertNotIn(address.pk, [p.pk for p in Property.needing_location()])
        self.client.post(
            reverse("crm:property_update", args=[address.pk]),
            self.fields(street="999 Somewhere Else"),
        )
        self.assertIn(address.pk, [p.pk for p in Property.needing_location()])

    def test_the_customers_offered_read_surname_first(self):
        labels = [
            str(label)
            for value, label in self.client.get(ADD).context["form"].fields["contact"].choices
            if value
        ]
        self.assertIn("Homeowner, Pat", labels)


class PrimaryAddressTests(PropertyTestCase):
    def test_choosing_a_main_address_steps_the_old_one_down(self):
        """Demote rather than refuse.

        One primary per customer is a partial unique index and it is not
        deferrable, so the old one has to step down before the new one
        is written. Refusing instead would be hit constantly, since the
        newest address is usually the main one.
        """
        old = self.address(street="1 Old St", primary=True)
        self.client.post(ADD, self.fields(street="2 New St", is_primary="on"))
        old.refresh_from_db()
        new = Property.objects.get(street="2 New St")
        self.assertEqual((old.is_primary, new.is_primary), (False, True))

    def test_only_one_address_is_ever_the_main_one(self):
        self.address(street="1 Old St", primary=True)
        self.client.post(ADD, self.fields(street="2 New St", is_primary="on"))
        self.assertEqual(Property.objects.filter(contact=self.customer, is_primary=True).count(), 1)

    def test_another_customers_main_address_is_untouched(self):
        other = Contact.objects.create(first_name="Sam", last_name="Else", created_by=self.rep)
        theirs = self.address(street="9 Their St", primary=True, contact=other)
        self.client.post(ADD, self.fields(street="2 New St", is_primary="on"))
        theirs.refresh_from_db()
        self.assertTrue(theirs.is_primary)

    def test_adding_a_second_address_without_ticking_it_changes_nothing(self):
        old = self.address(street="1 Old St", primary=True)
        self.client.post(ADD, self.fields(street="2 New St"))
        old.refresh_from_db()
        self.assertTrue(old.is_primary)


class ReturnTripTests(PropertyTestCase):
    """Adding a customer or address from the middle of booking a job."""

    def setUp(self):
        super().setUp()
        self.booking = reverse("jobs:job_create")

    def test_the_job_form_offers_both_quick_adds(self):
        page = self.client.get(self.booking)
        self.assertContains(page, reverse("crm:contact_create"))
        self.assertContains(page, reverse("crm:property_create"))

    def test_the_new_address_link_already_knows_the_customer(self):
        page = self.client.get(self.booking, {"contact": self.customer.pk})
        self.assertContains(page, f"contact={self.customer.pk}")

    def test_adding_an_address_comes_back_with_it_chosen(self):
        response = self.client.post(with_params(ADD, next=self.booking), self.fields(), follow=True)
        saved = Property.objects.get(street="12 Oak Ave")
        self.assertEqual(response.context["form"].initial.get("service_property"), saved.pk)

    def test_adding_a_customer_comes_back_with_them_chosen(self):
        response = self.client.post(
            with_params(reverse("crm:contact_create"), next=self.booking),
            {
                "first_name": "New",
                "last_name": "Person",
                "status": Contact.Status.CUSTOMER,
                "is_active": "on",
            },
            follow=True,
        )
        created = Contact.objects.get(last_name="Person")
        self.assertEqual(response.context["form"].initial.get("contact"), created.pk)

    def test_the_day_a_job_was_started_from_survives_the_trip(self):
        booking = f"{self.booking}?date=2026-11-03"
        response = self.client.post(with_params(ADD, next=booking), self.fields(), follow=True)
        self.assertIsNotNone(response.context["form"].initial.get("scheduled_start"))

    def test_a_next_pointing_off_this_site_is_ignored(self):
        response = self.client.post(with_params(ADD, next="https://evil.test/steal"), self.fields())
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.test", response["Location"])

    def test_a_scheme_relative_next_is_ignored(self):
        response = self.client.post(with_params(ADD, next="//evil.test/steal"), self.fields())
        self.assertNotIn("evil.test", response["Location"])

    def test_without_a_next_it_returns_to_the_customer(self):
        response = self.client.post(ADD, self.fields())
        self.assertRedirects(
            response, self.customer.get_absolute_url(), fetch_redirect_response=False
        )


class AccessTests(PropertyTestCase):
    def test_a_signed_out_visitor_cannot_add_an_address(self):
        self.client.logout()
        self.assertEqual(self.client.post(ADD, self.fields()).status_code, 302)
        self.assertFalse(Property.objects.exists())

    def test_a_crew_member_cannot_add_an_address(self):
        grant_role(User.objects.create_user("casey", password=PASSWORD), Role.CLEANER)
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.post(ADD, self.fields()).status_code, 403)
        self.assertFalse(Property.objects.exists())

    def test_somebody_with_no_role_cannot_add_an_address(self):
        User.objects.create_user("nobody", password=PASSWORD)
        self.client.login(username="nobody", password=PASSWORD)
        self.assertEqual(self.client.post(ADD, self.fields()).status_code, 403)

    def test_the_customer_page_offers_an_add_address_link(self):
        page = self.client.get(self.customer.get_absolute_url())
        self.assertContains(page, reverse("crm:property_create"))
