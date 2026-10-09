import json
from decimal import Decimal
from io import BytesIO, StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm import geocoding
from apps.crm.models import Property
from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"
MAP = reverse("jobs:map")


def answer(payload):
    """A stand-in for urlopen that returns one canned Nominatim reply."""

    class Response(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def opener(request, timeout=None):
        opener.calls.append(request)
        return Response(json.dumps(payload).encode())

    opener.calls = []
    return opener


def failing(error=OSError("no route to host")):
    def opener(request, timeout=None):
        raise error

    return opener


class MapTestCase(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.customer = f.contact(self.owner)
        self.address = Property.objects.create(
            contact=self.customer,
            street="12 Oak Ave",
            city="Oak Park",
            state="IL",
            postal_code="60301",
        )
        self.client.login(username="boss", password=PASSWORD)
        # Nothing in these tests should ever wait a real second.
        patcher = mock.patch.object(geocoding, "_wait_turn")
        self.addCleanup(patcher.stop)
        patcher.start()


class LookupTests(MapTestCase):
    def test_a_found_address_is_stored_with_what_it_was_looked_up_from(self):
        opener = answer([{"lat": "41.885", "lon": "-87.789"}])
        self.assertEqual(geocoding.locate(self.address, opener=opener), "located")
        self.address.refresh_from_db()
        self.assertEqual(self.address.latitude, Decimal("41.885000"))
        self.assertEqual(self.address.longitude, Decimal("-87.789000"))
        self.assertIsNotNone(self.address.located_at)
        self.assertEqual(self.address.located_address, str(self.address))
        self.assertFalse(self.address.needs_locating)

    def test_only_the_address_is_sent(self):
        opener = answer([{"lat": "1", "lon": "2"}])
        geocoding.locate(self.address, opener=opener)
        sent = opener.calls[0].full_url
        self.assertIn("12+Oak+Ave", sent)
        # Never the customer's name or anything else about them.
        self.assertNotIn("Pat", sent)
        self.assertNotIn("Homeowner", sent)

    def test_the_request_says_who_we_are(self):
        opener = answer([{"lat": "1", "lon": "2"}])
        geocoding.locate(self.address, opener=opener)
        agent = opener.calls[0].get_header("User-agent")
        self.assertIn("CRM", agent)
        self.assertTrue(agent)

    def test_an_address_nobody_knows_is_not_an_error(self):
        self.assertEqual(geocoding.locate(self.address, opener=answer([])), "not found")
        self.address.refresh_from_db()
        self.assertIsNone(self.address.latitude)

    def test_a_service_that_cannot_be_reached_is_an_error(self):
        # "We couldn't ask" must never be mistaken for "it isn't there".
        with self.assertRaises(geocoding.LookupError_):
            geocoding.locate(self.address, opener=failing())
        self.address.refresh_from_db()
        self.assertIsNone(self.address.latitude)

    def test_a_reply_we_do_not_understand_is_an_error(self):
        with self.assertRaises(geocoding.LookupError_):
            geocoding.lookup("anywhere", opener=answer([{"latitude": "nope"}]))

    def test_editing_an_address_re_opens_the_lookup(self):
        geocoding.locate(self.address, opener=answer([{"lat": "1", "lon": "2"}]))
        self.address.street = "14 Oak Ave"
        self.address.save(update_fields=["street"])
        self.assertTrue(self.address.needs_locating)

    def test_a_pin_dropped_by_hand(self):
        geocoding.place_by_hand(self.address, "41.5", "-87.5")
        self.address.refresh_from_db()
        self.assertEqual(self.address.latitude, Decimal("41.500000"))
        self.assertFalse(self.address.needs_locating)


class CommandTests(MapTestCase):
    def run_command(self, opener, **options):
        out = StringIO()
        with mock.patch("apps.crm.geocoding.urlopen", opener):
            call_command("locate_properties", stdout=out, stderr=StringIO(), **options)
        return out.getvalue()

    def test_it_places_what_has_no_coordinates(self):
        output = self.run_command(answer([{"lat": "41.8", "lon": "-87.7"}]))
        self.assertIn("Placed 1", output)
        self.address.refresh_from_db()
        self.assertTrue(self.address.is_located)

    def test_it_leaves_alone_what_is_already_placed(self):
        geocoding.place_by_hand(self.address, "41.5", "-87.5")
        output = self.run_command(answer([{"lat": "1", "lon": "2"}]))
        self.assertIn("already placed", output)

    def test_an_address_nobody_knows_is_reported_not_retried_forever(self):
        output = self.run_command(answer([]))
        self.assertIn("Not found", output)
        self.assertIn("not found 1", output)

    def test_a_service_error_is_counted_and_worth_retrying(self):
        output = self.run_command(failing())
        self.assertIn("service errors 1", output)
        self.assertIn("again later", output)


class MapPageTests(MapTestCase):
    def test_a_cleaner_is_refused(self):
        grant_role(f.user("casey"), Role.CLEANER)
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.get(MAP).status_code, 403)

    def test_an_unplaced_address_is_listed_with_a_way_to_place_it(self):
        response = self.client.get(MAP)
        self.assertEqual(response.context["unplaced_count"], 1)
        self.assertContains(response, "Look it up")
        self.assertContains(response, reverse("jobs:property_locate", args=[self.address.pk]))

    def test_a_placed_address_becomes_a_pin(self):
        geocoding.place_by_hand(self.address, "41.5", "-87.5")
        response = self.client.get(MAP)
        self.assertEqual(response.context["pin_count"], 1)
        pin = json.loads(response.context["pins_json"])[0]
        self.assertEqual((pin["lat"], pin["lng"]), (41.5, -87.5))
        self.assertEqual(pin["title"], str(self.customer))

    def test_a_pin_carries_the_next_job_booked_there(self):
        geocoding.place_by_hand(self.address, "41.5", "-87.5")
        start = timezone.localtime() + timezone.timedelta(hours=2)
        f.job(self.customer, self.owner, start=start, service_property=self.address, lines=[])
        pin = json.loads(self.client.get(MAP).context["pins_json"])[0]
        self.assertEqual(pin["jobs"], 1)
        self.assertTrue(pin["when"])
        self.assertTrue(pin["service"])

    def test_the_page_lists_every_pin_without_javascript(self):
        geocoding.place_by_hand(self.address, "41.5", "-87.5")
        response = self.client.get(MAP)
        self.assertContains(response, str(self.address))
        self.assertContains(response, self.customer.get_absolute_url())

    def add_addresses(self, how_many, placed=False):
        for number in range(how_many):
            address = Property.objects.create(
                contact=self.customer,
                street=f"{number} Elm St",
                city="Oak Park",
                state="IL",
                postal_code="60301",
            )
            if placed:
                geocoding.place_by_hand(address, "41.5", "-87.5")

    def test_which_addresses_need_placing_is_a_database_question(self):
        # Not "load them all and filter in Python": the page must be
        # able to count and slice without fetching every row.
        self.add_addresses(4)
        self.add_addresses(3, placed=True)
        pending = Property.needing_location()
        self.assertEqual(pending.count(), 5)  # four new, plus the one from setUp
        self.assertEqual(len(pending[:2]), 2)
        self.assertIn("LIMIT", str(pending[:2].query).upper())
        self.assertIn("WHERE", str(pending.query).upper())

    def test_the_page_counts_and_slices_rather_than_listing_everything(self):
        self.add_addresses(40)
        self.add_addresses(3, placed=True)
        context = self.client.get(MAP).context
        self.assertEqual(context["unplaced_count"], 41)
        self.assertEqual(len(context["unplaced"]), 25)  # the page's cap
        self.assertEqual(context["unplaced_more"], 16)
        self.assertEqual(context["pin_count"], 3)

    def test_an_edited_address_is_asked_about_again(self):
        geocoding.place_by_hand(self.address, "41.5", "-87.5")
        self.assertEqual(self.client.get(MAP).context["unplaced_count"], 0)
        self.address.street = "14 Oak Ave"
        self.address.save(update_fields=["street"])
        self.assertEqual(self.client.get(MAP).context["unplaced_count"], 1)

    def test_nothing_is_looked_up_while_the_page_renders(self):
        # A page must never wait on a third party.
        with mock.patch("apps.crm.geocoding.urlopen") as urlopen:
            self.client.get(MAP)
        urlopen.assert_not_called()


class LocateViewTests(MapTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("jobs:property_locate", args=[self.address.pk])

    def test_looking_one_up_from_the_page(self):
        with mock.patch("apps.crm.geocoding.urlopen", answer([{"lat": "41.5", "lon": "-87.5"}])):
            response = self.client.post(self.url, follow=True)
        self.assertContains(response, "Found")
        self.address.refresh_from_db()
        self.assertTrue(self.address.is_located)

    def test_an_address_nobody_knows_says_so_and_offers_the_pin(self):
        with mock.patch("apps.crm.geocoding.urlopen", answer([])):
            response = self.client.post(self.url, follow=True)
        self.assertContains(response, "Drop the pin yourself")

    def test_a_service_that_is_down_says_so(self):
        with mock.patch("apps.crm.geocoding.urlopen", failing()):
            response = self.client.post(self.url, follow=True)
        self.assertContains(response, "Couldn&#x27;t reach OpenStreetMap")

    def test_dropping_a_pin_by_hand_never_leaves_this_server(self):
        with mock.patch("apps.crm.geocoding.urlopen") as urlopen:
            response = self.client.post(self.url, {"lat": "41.5", "lng": "-87.5"}, follow=True)
        urlopen.assert_not_called()
        self.assertContains(response, "Pinned")
        self.address.refresh_from_db()
        self.assertEqual(self.address.latitude, Decimal("41.500000"))

    def test_nonsense_coordinates_are_refused(self):
        response = self.client.post(self.url, {"lat": "over there", "lng": "x"}, follow=True)
        self.assertContains(response, "point on the map")
        self.address.refresh_from_db()
        self.assertFalse(self.address.is_located)

    def test_a_cleaner_cannot_place_anything(self):
        grant_role(f.user("casey"), Role.CLEANER)
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.post(self.url).status_code, 403)

    def test_get_does_nothing(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class MapSearchTests(MapTestCase):
    """Finding one customer or one street on a map full of pins."""

    def setUp(self):
        super().setUp()
        self.address.latitude, self.address.longitude = Decimal("43.1"), Decimal("-77.6")
        self.address.located_address = str(self.address)
        self.address.save()
        self.other = Property.objects.create(
            contact=f.contact(self.owner, first="Sam", last="Elsewhere"),
            street="99 Ridge Rd",
            city="Webster",
            state="NY",
            postal_code="14580",
            latitude=Decimal("43.2"),
            longitude=Decimal("-77.4"),
        )
        self.other.located_address = str(self.other)
        self.other.save()

    def page(self, **params):
        response = self.client.get(MAP, params)
        self.assertEqual(response.status_code, 200)
        return response

    def addresses_on(self, response):
        return {pin["address"] for pin in response.context["pins"]}

    def test_without_a_search_every_placed_address_is_shown(self):
        self.assertEqual(len(self.addresses_on(self.page())), 2)

    def test_it_can_be_narrowed_by_customer_name(self):
        shown = self.addresses_on(self.page(q="Elsewhere"))
        self.assertEqual(shown, {str(self.other)})

    def test_it_can_be_narrowed_by_street(self):
        self.assertEqual(self.addresses_on(self.page(q="Ridge")), {str(self.other)})

    def test_it_can_be_narrowed_by_town(self):
        self.assertEqual(self.addresses_on(self.page(q="Webster")), {str(self.other)})

    def test_it_can_be_narrowed_by_postcode(self):
        self.assertEqual(self.addresses_on(self.page(q="14580")), {str(self.other)})

    def test_the_search_ignores_capitalisation(self):
        self.assertEqual(self.addresses_on(self.page(q="webster")), {str(self.other)})

    def test_a_search_matching_nothing_says_so(self):
        response = self.page(q="nowhere-at-all")
        self.assertEqual(self.addresses_on(response), set())
        self.assertContains(response, "Nothing matched")

    def test_the_search_also_narrows_the_list_still_to_place(self):
        waiting = Property.objects.create(
            contact=f.contact(self.owner, first="Pat", last="Waiting"),
            street="5 Holt Rd",
            city="Webster",
            state="NY",
            postal_code="14580",
        )
        elsewhere = Property.objects.create(
            contact=f.contact(self.owner, first="Other", last="Person"),
            street="7 Main St",
            city="Fairport",
            state="NY",
            postal_code="14450",
        )
        shown = [p.pk for p in self.page(q="Webster").context["unplaced"]]
        self.assertIn(waiting.pk, shown)
        self.assertNotIn(elsewhere.pk, shown)

    def test_the_count_matches_what_the_search_found(self):
        response = self.page(q="Webster")
        self.assertEqual(response.context["pin_count"], 1)
        self.assertEqual(response.context["pins_capped"], 0)

    def test_the_box_keeps_what_was_typed(self):
        response = self.page(q="Webster")
        self.assertEqual(response.context["query"], "Webster")
        self.assertContains(response, 'value="Webster"')

    def test_surrounding_spaces_are_ignored(self):
        self.assertEqual(self.addresses_on(self.page(q="  Webster  ")), {str(self.other)})


class PlacedAgainTests(MapTestCase):
    """An address already on the map can be looked up again.

    Correcting a street after it was pinned would otherwise keep the old
    location for ever.
    """

    def setUp(self):
        super().setUp()
        self.address.latitude, self.address.longitude = Decimal("43.1"), Decimal("-77.6")
        self.address.located_address = str(self.address)
        self.address.save()

    def test_the_page_offers_to_look_a_placed_address_up_again(self):
        response = self.client.get(MAP)
        self.assertContains(response, reverse("jobs:property_locate", args=[self.address.pk]))
        self.assertContains(response, "Look it up again")

    def test_looking_it_up_again_moves_the_pin(self):
        with mock.patch.object(geocoding, "urlopen", answer([{"lat": "44.0", "lon": "-78.0"}])):
            self.client.post(reverse("jobs:property_locate", args=[self.address.pk]))
        self.address.refresh_from_db()
        self.assertEqual(float(self.address.latitude), 44.0)


class PinByHandTests(MapTestCase):
    """The pin-drop the page has promised since Phase 17.5.

    `geocoding.place_by_hand` and the view's lat/lng branch have both
    worked all along, and ADR 0011 said an address Nominatim can't find
    "can be pinned by tapping the map" — but nothing in the interface
    ever submitted it.
    """

    def test_the_page_offers_a_way_to_type_the_point(self):
        response = self.client.get(MAP)
        self.assertContains(response, 'name="lat"')
        self.assertContains(response, 'name="lng"')
        self.assertContains(response, "Pin it")

    def test_an_address_can_be_placed_by_typing_coordinates(self):
        self.client.post(
            reverse("jobs:property_locate", args=[self.address.pk]),
            {"lat": "43.123456", "lng": "-77.654321"},
        )
        self.address.refresh_from_db()
        self.assertEqual(
            (float(self.address.latitude), float(self.address.longitude)),
            (43.123456, -77.654321),
        )
        self.assertIsNotNone(self.address.located_at)

    def test_typing_the_point_never_leaves_this_server(self):
        with mock.patch.object(geocoding, "urlopen") as opener:
            self.client.post(
                reverse("jobs:property_locate", args=[self.address.pk]),
                {"lat": "43.1", "lng": "-77.6"},
            )
        opener.assert_not_called()

    def test_rubbish_coordinates_are_refused(self):
        self.client.post(
            reverse("jobs:property_locate", args=[self.address.pk]),
            {"lat": "over there", "lng": "somewhere"},
        )
        self.address.refresh_from_db()
        self.assertIsNone(self.address.latitude)

    def test_the_form_works_without_javascript(self):
        """The two boxes are real fields, not filled only by a script.

        static/js/map.js writes into them on a map click; the point is
        that they are submittable on their own.
        """
        response = self.client.get(MAP)
        self.assertContains(response, "data-pin-form")
        self.assertContains(response, 'type="submit"')
        self.assertNotContains(response, "js-only")
