"""Narrowing Customers and Companies by where the work is.

The trap this file exists to guard: filtering by joining `properties`
multiplies the rows, because a customer with two addresses in one town
matches twice. The rows look wrong AND `paginator.count` goes wrong,
and on page one with few customers it still looks fine. So every test
here that counts rows also checks the number the page reports.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.crm.models import Company, Contact, Property
from apps.crm.tests._helpers import grant_role

User = get_user_model()
PASSWORD = "correct-horse-battery"

CUSTOMERS = reverse("crm:contact_list")
COMPANIES = reverse("crm:company_list")


class AddressFilterTestCase(TestCase):
    def setUp(self):
        self.user = grant_role(User.objects.create_user("rep", password=PASSWORD))
        self.client.login(username="rep", password=PASSWORD)

    def company(self, name):
        return Company.objects.create(name=name, created_by=self.user)

    def customer(self, first, last, company=None):
        return Contact.objects.create(
            first_name=first, last_name=last, created_by=self.user, company=company
        )

    def address(self, contact, city, postal="14526", street="1 Any St"):
        return Property.objects.create(
            contact=contact, street=street, city=city, state="NY", postal_code=postal
        )

    def listing(self, url, **params):
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200)
        return response


class CustomerAddressFilterTests(AddressFilterTestCase):
    def test_customers_can_be_narrowed_to_a_town(self):
        here = self.customer("Pat", "Here")
        self.address(here, "Penfield")
        away = self.customer("Sam", "Away")
        self.address(away, "Webster")
        shown = self.listing(CUSTOMERS, town="Penfield").context["contacts"]
        self.assertEqual([c.pk for c in shown], [here.pk])

    def test_the_town_match_ignores_capitalisation(self):
        here = self.customer("Pat", "Here")
        self.address(here, "Penfield")
        shown = self.listing(CUSTOMERS, town="penfield").context["contacts"]
        self.assertEqual([c.pk for c in shown], [here.pk])

    def test_customers_can_be_narrowed_to_a_postal_code(self):
        here = self.customer("Pat", "Here")
        self.address(here, "Penfield", postal="14526")
        away = self.customer("Sam", "Away")
        self.address(away, "Webster", postal="14580")
        shown = self.listing(CUSTOMERS, postal="14526").context["contacts"]
        self.assertEqual([c.pk for c in shown], [here.pk])

    def test_a_customer_with_two_addresses_in_the_town_appears_once(self):
        # The duplication a join would cause.
        twice = self.customer("Pat", "Twice")
        self.address(twice, "Penfield", street="1 First St")
        self.address(twice, "Penfield", street="2 Second St")
        response = self.listing(CUSTOMERS, town="Penfield")
        self.assertEqual([c.pk for c in response.context["contacts"]], [twice.pk])

    def test_the_number_reported_matches_the_rows_shown(self):
        """The half of the bug a row count alone would miss.

        A join gives the right-looking page and a wrong total, so this
        asserts the paginator's own figure.
        """
        twice = self.customer("Pat", "Twice")
        self.address(twice, "Penfield", street="1 First St")
        self.address(twice, "Penfield", street="2 Second St")
        response = self.listing(CUSTOMERS, town="Penfield")
        self.assertEqual(response.context["paginator"].count, 1)
        self.assertEqual(len(response.context["contacts"]), 1)

    def test_a_town_and_a_postcode_must_match_the_same_address(self):
        """Both together mean one address matching both, not either.

        A customer with a home in one town and a rental in another does
        not match a town from the first and a postcode from the second.
        Written down because "both filters at once" has two plausible
        readings and the code has to pick one.
        """
        split = self.customer("Pat", "Split")
        self.address(split, "Penfield", postal="14526", street="1 Home St")
        self.address(split, "Webster", postal="14580", street="2 Rental Rd")
        crossed = self.listing(CUSTOMERS, town="Penfield", postal="14580")
        self.assertEqual(len(crossed.context["contacts"]), 0)
        together = self.listing(CUSTOMERS, town="Penfield", postal="14526")
        self.assertEqual([c.pk for c in together.context["contacts"]], [split.pk])

    def test_a_customer_with_no_address_is_left_out(self):
        self.customer("No", "Address")
        self.assertEqual(len(self.listing(CUSTOMERS, town="Penfield").context["contacts"]), 0)

    def test_an_unknown_town_matches_nobody(self):
        here = self.customer("Pat", "Here")
        self.address(here, "Penfield")
        self.assertEqual(len(self.listing(CUSTOMERS, town="Nowhere").context["contacts"]), 0)

    def test_the_town_and_the_search_box_combine(self):
        wanted = self.customer("Pat", "Here")
        self.address(wanted, "Penfield")
        other = self.customer("Sam", "Alsohere")
        self.address(other, "Penfield")
        shown = self.listing(CUSTOMERS, town="Penfield", q="Pat").context["contacts"]
        self.assertEqual([c.pk for c in shown], [wanted.pk])

    def test_the_town_choices_offer_only_towns_somebody_lives_in(self):
        here = self.customer("Pat", "Here")
        self.address(here, "Penfield")
        towns = list(self.listing(CUSTOMERS).context["towns"])
        self.assertEqual(towns, ["Penfield"])

    def test_the_chosen_town_is_still_selected_afterwards(self):
        here = self.customer("Pat", "Here")
        self.address(here, "Penfield")
        response = self.listing(CUSTOMERS, town="Penfield")
        self.assertEqual(response.context["town"], "Penfield")
        self.assertContains(response, 'value="Penfield" selected')

    def test_the_town_survives_paging(self):
        for i in range(30):
            customer = self.customer(f"Pat{i}", "Here")
            self.address(customer, "Penfield")
        away = self.customer("Sam", "Away")
        self.address(away, "Webster")
        page_two = self.listing(CUSTOMERS, town="Penfield", page="2")
        self.assertEqual(page_two.context["paginator"].count, 30)
        self.assertNotIn(away.pk, [c.pk for c in page_two.context["contacts"]])

    def test_filtering_by_town_costs_no_query_per_customer(self):
        """The cost must not grow with the number of customers.

        Asserted by comparing two sizes rather than by pinning a
        measured number: a hardcoded count taken from a run of the code
        passes whatever that code does, which is a mistake already made
        once in this project.
        """

        def queries_for(count):
            Property.objects.all().delete()
            Contact.objects.all().delete()
            for i in range(count):
                self.address(self.customer(f"Pat{i}", "Here"), "Penfield")
            with CaptureQueriesContext(connection) as captured:
                self.client.get(CUSTOMERS, {"town": "Penfield"})
            return len(captured.captured_queries)

        few, many = queries_for(3), queries_for(18)
        self.assertEqual(few, many, f"{few} queries for 3 customers, {many} for 18")


class CompanyAddressFilterTests(AddressFilterTestCase):
    """A company has no address of its own, so it matches where its
    customers are."""

    def test_a_company_matches_when_one_of_its_customers_lives_there(self):
        wanted = self.company("Here Ltd")
        self.address(self.customer("Pat", "Here", company=wanted), "Penfield")
        other = self.company("Away Ltd")
        self.address(self.customer("Sam", "Away", company=other), "Webster")
        shown = self.listing(COMPANIES, town="Penfield").context["companies"]
        self.assertEqual([c.pk for c in shown], [wanted.pk])

    def test_a_company_with_two_matching_customers_appears_once(self):
        wanted = self.company("Here Ltd")
        self.address(self.customer("Pat", "Here", company=wanted), "Penfield")
        self.address(self.customer("Sam", "Alsohere", company=wanted), "Penfield")
        response = self.listing(COMPANIES, town="Penfield")
        self.assertEqual([c.pk for c in response.context["companies"]], [wanted.pk])
        self.assertEqual(response.context["paginator"].count, 1)

    def test_a_company_with_one_customer_at_two_addresses_appears_once(self):
        wanted = self.company("Here Ltd")
        customer = self.customer("Pat", "Here", company=wanted)
        self.address(customer, "Penfield", street="1 First St")
        self.address(customer, "Penfield", street="2 Second St")
        response = self.listing(COMPANIES, town="Penfield")
        self.assertEqual(response.context["paginator"].count, 1)

    def test_a_company_with_no_customers_is_left_out(self):
        self.company("Empty Ltd")
        self.assertEqual(len(self.listing(COMPANIES, town="Penfield").context["companies"]), 0)

    def test_a_customer_with_no_company_pulls_nothing_in(self):
        # A contact with company=None must not match every company, nor
        # produce a row for a null company.
        self.address(self.customer("Pat", "Nocompany"), "Penfield")
        self.company("Unrelated Ltd")
        self.assertEqual(len(self.listing(COMPANIES, town="Penfield").context["companies"]), 0)

    def test_companies_can_be_narrowed_to_a_postal_code(self):
        wanted = self.company("Here Ltd")
        self.address(self.customer("Pat", "Here", company=wanted), "Penfield", postal="14526")
        other = self.company("Away Ltd")
        self.address(self.customer("Sam", "Away", company=other), "Webster", postal="14580")
        shown = self.listing(COMPANIES, postal="14526").context["companies"]
        self.assertEqual([c.pk for c in shown], [wanted.pk])

    def test_the_town_and_the_name_search_combine(self):
        wanted = self.company("Here Ltd")
        self.address(self.customer("Pat", "Here", company=wanted), "Penfield")
        other = self.company("Other Ltd")
        self.address(self.customer("Sam", "Alsohere", company=other), "Penfield")
        shown = self.listing(COMPANIES, town="Penfield", q="Here").context["companies"]
        self.assertEqual([c.pk for c in shown], [wanted.pk])
