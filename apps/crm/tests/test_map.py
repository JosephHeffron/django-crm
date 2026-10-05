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
