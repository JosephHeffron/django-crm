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

    def test_customers_can_be_found_by_part_of_a_street(self):
        """The thing the exact-match postcode box could not do."""
        here = self.customer("Pat", "Here")
        self.address(here, "Penfield", street="118 Castlebar Rd")
        away = self.customer("Sam", "Away")
        self.address(away, "Penfield", street="7 Elm Ave")
        shown = self.listing(CUSTOMERS, address="castlebar").context["contacts"]
        self.assertEqual([c.pk for c in shown], [here.pk])

    def test_the_address_search_also_matches_a_town(self):
        here = self.customer("Pat", "Here")
        self.address(here, "Penfield")
        away = self.customer("Sam", "Away")
        self.address(away, "Webster")
        shown = self.listing(CUSTOMERS, address="penf").context["contacts"]
        self.assertEqual([c.pk for c in shown], [here.pk])

    def test_the_address_search_matches_part_of_a_postcode(self):
        """Partial, unlike the box it replaced, which needed the lot."""
        here = self.customer("Pat", "Here")
        self.address(here, "Penfield", postal="14526")
        away = self.customer("Sam", "Away")
        self.address(away, "Webster", postal="14580")
        shown = self.listing(CUSTOMERS, address="145 2").context["contacts"]
        self.assertEqual(shown.count(), 0, "a space-separated fragment should not match")
        shown = self.listing(CUSTOMERS, address="1452").context["contacts"]
        self.assertEqual([c.pk for c in shown], [here.pk])

    def test_a_customer_with_two_matching_addresses_appears_once(self):
        """The join bug, in the form this filter is most likely to hit.

        Two addresses on the same street both match `address=elm`. A
        join would list the customer twice and report 2; the row count
        alone would look right on a page of one.
        """
        both = self.customer("Pat", "Twice")
        self.address(both, "Penfield", street="3 Elm Ave")
        self.address(both, "Webster", street="9 Elm Rd")
        response = self.listing(CUSTOMERS, address="elm")
        shown = response.context["contacts"]
        self.assertEqual([c.pk for c in shown], [both.pk])
        self.assertEqual(response.context["paginator"].count, 1)

    def test_a_town_and_an_address_must_match_the_same_address(self):
        """Why this is a third filter and not a second subquery.

        Pat has a home in Penfield and a rental on Elm St in Webster.
        Neither address is both, so `?town=Penfield&address=Elm` must
        not find them. Two independent `pk__in` subqueries would, and
        that is the reading
        `test_a_town_and_a_postcode_must_match_the_same_address`
        already rejected for town plus postcode.
        """
        pat = self.customer("Pat", "Split")
        self.address(pat, "Penfield", street="1 Home Way")
        self.address(pat, "Webster", street="2 Elm St")
        shown = self.listing(CUSTOMERS, town="Penfield", address="Elm").context["contacts"]
        self.assertEqual(shown.count(), 0)

        # And the other way: one address satisfying both does match.
        sam = self.customer("Sam", "Both")
        self.address(sam, "Penfield", street="4 Elm Close")
        shown = self.listing(CUSTOMERS, town="Penfield", address="Elm").context["contacts"]
        self.assertEqual([c.pk for c in shown], [sam.pk])

    def test_the_address_asked_for_comes_back_to_the_box(self):
        response = self.listing(CUSTOMERS, address="castlebar")
        self.assertEqual(response.context["address"], "castlebar")
        self.assertContains(response, 'value="castlebar"')

    def test_an_old_postcode_bookmark_still_filters(self):
        """Its input is gone from the page; the URL must keep working."""
        here = self.customer("Pat", "Here")
        self.address(here, "Penfield", postal="14526")
        away = self.customer("Sam", "Away")
        self.address(away, "Webster", postal="14580")
        shown = self.listing(CUSTOMERS, postal="14526").context["contacts"]
        self.assertEqual([c.pk for c in shown], [here.pk])

    def test_the_address_filter_survives_paging(self):
        """Page two has to be filtered too.

        The first version of this seeded 30 matching customers and
        nothing else, so dropping the filter when building page two
        left the same 30 rows and the same count — it passed either
        way. Sourcery caught that on PR #165. The non-matching dozen
        is what makes it bite: unfiltered, the count would be 42 and
        page two would be full of Oak Dr.
        """
        for i in range(30):
            self.address(self.customer(f"Pat{i}", "Here"), "Penfield", street=f"{i} Elm Ave")
        for i in range(12):
            self.address(self.customer(f"Sam{i}", "Away"), "Webster", street=f"{i} Oak Dr")
        response = self.listing(CUSTOMERS, address="elm", page=2)
        self.assertEqual(response.context["paginator"].count, 30)
        shown = list(response.context["contacts"])
        self.assertEqual(len(shown), 5, "25 on page one, the rest here")
        self.assertEqual([c.last_name for c in shown], ["Here"] * 5)

    def test_an_old_postcode_bookmark_shows_up_in_the_address_box(self):
        """So the page admits what it is filtering by.

        The postcode input is gone, and `?postal=` still filters, so
        without this the box read empty while the results were
        narrowed — and pressing Filter dropped the postcode and
        widened them with nothing on the page to explain it.
        """
        response = self.listing(CUSTOMERS, postal="14526")
        self.assertEqual(response.context["address"], "14526")
        self.assertContains(response, 'value="14526"')

    def test_resubmitting_the_box_keeps_the_same_customers(self):
        """The other half: what the box hands back has to still work.

        `?postal=` matches exactly and `?address=` matches partially,
        so these are not the same query — this pins that they pick the
        same people for a whole postcode, which is the only kind of
        value the box can be handed this way.
        """
        here = self.customer("Pat", "Here")
        self.address(here, "Penfield", postal="14526")
        away = self.customer("Sam", "Away")
        self.address(away, "Webster", postal="14580")

        bookmarked = self.listing(CUSTOMERS, postal="14526")
        echoed = bookmarked.context["address"]
        resubmitted = self.listing(CUSTOMERS, address=echoed)
        self.assertEqual(
            [c.pk for c in resubmitted.context["contacts"]],
            [c.pk for c in bookmarked.context["contacts"]],
        )
        self.assertEqual([c.pk for c in resubmitted.context["contacts"]], [here.pk])

    def test_the_address_shows_in_the_row(self):
        pat = self.customer("Pat", "Here")
        self.address(pat, "Penfield", street="118 Castlebar Rd")
        response = self.listing(CUSTOMERS)
        self.assertContains(response, "118 Castlebar Rd, Penfield")

    def test_a_customer_with_no_address_still_renders(self):
        self.customer("Pat", "Nowhere")
        self.assertContains(self.listing(CUSTOMERS), "Nowhere")

    def test_the_row_shows_the_main_address_and_counts_the_rest(self):
        """The main one, not merely the first one by street.

        The streets are named so that the main address sorts **last**
        alphabetically. Written the other way round the test passes
        even with `Property.Meta.ordering` cut down to `["street"]`,
        which is what makes `is_primary` the reason this works —
        confirmed by mutating that `Meta.ordering` and watching this
        test go from green to red.
        """
        pat = self.customer("Pat", "Several")
        self.address(pat, "Webster", street="1 Second St")
        main = self.address(pat, "Penfield", street="9 Main St")
        main.is_primary = True
        main.save(update_fields=["is_primary"])
        response = self.listing(CUSTOMERS)
        self.assertContains(response, "9 Main St, Penfield")
        self.assertContains(response, "+1 more")
        self.assertNotContains(response, "1 Second St")

    def test_showing_the_address_costs_no_query_per_customer(self):
        """The N+1 this column would introduce if written with `.first`
        and without the prefetch. Compared at two sizes rather than
        pinned to a measured number."""

        def queries_for(count):
            Property.objects.all().delete()
            Contact.objects.all().delete()
            for i in range(count):
                self.address(self.customer(f"Pat{i}", "Here"), "Penfield", street=f"{i} Elm Ave")
            with CaptureQueriesContext(connection) as captured:
                self.client.get(CUSTOMERS)
            return len(captured.captured_queries)

        few, many = queries_for(3), queries_for(18)
        self.assertEqual(few, many, f"{few} queries for 3 customers, {many} for 18")

    def test_filtering_by_address_costs_no_query_per_customer(self):
        def queries_for(count):
            Property.objects.all().delete()
            Contact.objects.all().delete()
            for i in range(count):
                self.address(self.customer(f"Pat{i}", "Here"), "Penfield", street=f"{i} Elm Ave")
            with CaptureQueriesContext(connection) as captured:
                self.client.get(CUSTOMERS, {"address": "elm"})
            return len(captured.captured_queries)

        few, many = queries_for(3), queries_for(18)
        self.assertEqual(few, many, f"{few} queries for 3 customers, {many} for 18")

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
