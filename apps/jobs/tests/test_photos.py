"""Adding, showing and removing job and estimate photos (Phase 18 unit 2).

Unit 1 built the serving side: a login-gated view that checks whether
you may see the job a photo belongs to. Nothing uploaded or displayed
one until now.

The tests that matter most are the processing ones. A phone photo of a
customer's house carries their GPS coordinates in its metadata, and
ADR 0009 promised that stripping while nothing implemented it. If
`process_photo` ever stops re-encoding, the stored file carries the
customer's home address and no page would look any different.
"""

import io
import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.crm.models import AuditLogEntry
from apps.crm.tests._helpers import grant_role
from apps.jobs import photos as photo_service
from apps.jobs.models import Photo
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"


def photo_bytes(size=(1200, 900), fmt="JPEG", exif=None, colour="#4c8f6b"):
    image = Image.new("RGB", size, colour)
    out = io.BytesIO()
    if exif is not None:
        tags = image.getexif()
        for key, value in exif.items():
            tags[key] = value
        image.save(out, format=fmt, exif=tags.tobytes())
    else:
        image.save(out, format=fmt)
    return out.getvalue()


def upload(name="IMG_0001.jpg", **kwargs):
    return SimpleUploadedFile(name, photo_bytes(**kwargs), content_type="image/jpeg")


class ProcessingTests(TestCase):
    """What happens to the bytes before they are stored."""

    def stored(self, uploaded):
        processed = photo_service.process_photo(uploaded)
        data = processed.read()
        processed.seek(0)
        return processed, Image.open(io.BytesIO(data)), data

    def test_the_location_is_stripped(self):
        """The reason this module re-encodes at all.

        EXIF GPS on a photo of somebody's house is their home address,
        in a file staff can open. ADR 0009 promised this and nothing
        had done it.
        """
        # 34853 is the GPS IFD pointer; 271 is the camera make.
        uploaded = upload(exif={271: "ACME Phone", 274: 1})
        _, image, _ = self.stored(uploaded)
        self.assertEqual(dict(image.getexif()), {})

    def test_nothing_of_the_original_bytes_survives(self):
        # Belt and braces: the stored file is one this code produced.
        raw = photo_bytes(exif={271: "ACME Phone"})
        _, _, data = self.stored(SimpleUploadedFile("IMG_1.jpg", raw, content_type="image/jpeg"))
        self.assertNotEqual(data, raw)
        self.assertNotIn(b"ACME Phone", data)

    def test_a_big_photo_is_shrunk(self):
        _, image, _ = self.stored(upload(size=(4032, 3024)))
        self.assertEqual(max(image.size), photo_service.MAX_EDGE)
        self.assertEqual(image.size, (2000, 1500))

    def test_a_small_photo_is_left_its_own_size(self):
        _, image, _ = self.stored(upload(size=(800, 600)))
        self.assertEqual(image.size, (800, 600))

    def test_a_sideways_photo_is_turned_the_right_way_up(self):
        """Orientation lives in the EXIF that is about to be discarded.

        So it has to be applied first, or every portrait photo from a
        phone comes out on its side.
        """
        # Orientation 6 means "rotate 90": a landscape file is really
        # a portrait photo.
        _, image, _ = self.stored(upload(size=(1200, 900), exif={274: 6}))
        self.assertGreater(image.height, image.width)

    def test_the_stored_file_is_always_a_jpeg(self):
        processed, image, _ = self.stored(
            SimpleUploadedFile("shot.png", photo_bytes(fmt="PNG"), content_type="image/png")
        )
        self.assertEqual(image.format, "JPEG")
        self.assertEqual(processed.name, "photo.jpg")

    def test_a_png_with_transparency_does_not_blow_up(self):
        transparent = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
        out = io.BytesIO()
        transparent.save(out, format="PNG")
        _, image, _ = self.stored(
            SimpleUploadedFile("t.png", out.getvalue(), content_type="image/png")
        )
        self.assertEqual(image.mode, "RGB")

    def test_a_heic_photo_says_what_to_do_about_it(self):
        """An iPhone shoots HEIC by default and Pillow here can't read it.

        "That file isn't a photo we can read" would be a poor answer
        about a photograph, so the message says what to change.
        """
        with self.assertRaises(ValidationError) as caught:
            photo_service.process_photo(
                SimpleUploadedFile(
                    "IMG_0002.HEIC", b"ftypheic not really", content_type="image/heic"
                )
            )
        message = " ".join(caught.exception.messages)
        self.assertIn("HEIC", message)
        self.assertIn("Most Compatible", message)

    def test_something_that_is_not_an_image_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            photo_service.process_photo(
                SimpleUploadedFile("notes.txt", b"just words", content_type="text/plain")
            )
        self.assertIn("isn't a photo", " ".join(caught.exception.messages))

    def test_an_enormous_file_is_refused_before_it_is_decoded(self):
        huge = SimpleUploadedFile("big.jpg", b"x" * 10, content_type="image/jpeg")
        huge.size = photo_service.MAX_UPLOAD_BYTES + 1
        with self.assertRaises(ValidationError) as caught:
            photo_service.process_photo(huge)
        self.assertIn("MB", " ".join(caught.exception.messages))


class PhotoTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media = tempfile.mkdtemp()
        cls.override = override_settings(MEDIA_ROOT=cls.media)
        cls.override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.override.disable()
        shutil.rmtree(cls.media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.casey = grant_role(f.user("casey", first_name="Casey"), Role.CLEANER)
        self.alex = grant_role(f.user("alex", first_name="Alex"), Role.CLEANER)
        self.customer = f.contact(self.owner)
        self.job = f.job(self.customer, self.owner, lines=[])
        f.assign(self.job, self.casey)
        self.quote = f.quote(self.customer, self.owner)
        self.add_url = reverse("jobs:job_photo_add", args=[self.job.pk])

    def add(self, url=None, kind=Photo.Kind.BEFORE, caption="", name="IMG_0001.jpg"):
        return self.client.post(
            url or self.add_url,
            {"image": upload(name=name), "kind": kind, "caption": caption},
        )


class AddingTests(PhotoTestCase):
    def test_a_crew_member_on_the_job_can_add_a_photo(self):
        self.client.login(username="casey", password=PASSWORD)
        self.add(caption="Gutters before")
        photo = Photo.objects.get()
        self.assertEqual(
            (photo.job_id, photo.kind, photo.caption, photo.uploaded_by_id),
            (self.job.pk, Photo.Kind.BEFORE, "Gutters before", self.casey.pk),
        )

    def test_the_stored_file_is_the_processed_one(self):
        self.client.login(username="casey", password=PASSWORD)
        self.add()
        photo = Photo.objects.get()
        self.assertTrue(photo.image.name.endswith(".jpg"))
        self.assertTrue(photo.image.name.startswith("private/photos/"))
        self.assertIn(str(photo.uuid), photo.image.name)

    def test_the_owner_can_add_to_any_job(self):
        self.client.login(username="boss", password=PASSWORD)
        self.add()
        self.assertEqual(Photo.objects.count(), 1)

    def test_a_crew_member_on_another_job_is_not_found(self):
        # 404, never 403: a 403 would confirm the job exists.
        self.client.login(username="alex", password=PASSWORD)
        self.assertEqual(self.add().status_code, 404)
        self.assertEqual(Photo.objects.count(), 0)

    def test_a_signed_out_visitor_is_sent_to_sign_in(self):
        self.assertEqual(self.add().status_code, 302)
        self.assertEqual(Photo.objects.count(), 0)

    def test_an_estimate_photo_is_filed_against_the_estimate(self):
        self.client.login(username="boss", password=PASSWORD)
        self.add(
            url=reverse("jobs:quote_photo_add", args=[self.quote.pk]),
            kind=Photo.Kind.REFERENCE,
        )
        photo = Photo.objects.get()
        self.assertEqual((photo.quote_id, photo.job_id), (self.quote.pk, None))

    def test_a_crew_member_cannot_add_to_an_estimate(self):
        # Crews don't see estimates at all (apps/jobs/access.py).
        self.client.login(username="casey", password=PASSWORD)
        response = self.add(
            url=reverse("jobs:quote_photo_add", args=[self.quote.pk]),
            kind=Photo.Kind.REFERENCE,
        )
        self.assertEqual(response.status_code, 404)

    def test_a_heic_upload_is_explained_rather_than_saved(self):
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.post(
            self.add_url,
            {
                "image": SimpleUploadedFile(
                    "IMG_9.HEIC", b"ftypheic not really", content_type="image/heic"
                ),
                "kind": Photo.Kind.BEFORE,
            },
            follow=True,
        )
        self.assertEqual(Photo.objects.count(), 0)
        self.assertIn("HEIC", " ".join(str(m) for m in response.context["messages"]))

    def test_adding_a_photo_is_recorded_in_the_change_log(self):
        self.client.login(username="casey", password=PASSWORD)
        self.add()
        self.assertTrue(
            AuditLogEntry.objects.filter(
                content_type__model="photo", action=AuditLogEntry.Action.CREATED
            ).exists()
        )

    def test_it_returns_to_the_photos_on_the_job(self):
        self.client.login(username="casey", password=PASSWORD)
        response = self.add()
        self.assertRedirects(
            response, f"{self.job.get_absolute_url()}#photos", fetch_redirect_response=False
        )


class ShowingTests(PhotoTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="casey", password=PASSWORD)
        self.add(caption="Gutters before")
        self.photo = Photo.objects.get()

    def test_the_job_page_shows_the_photo(self):
        response = self.client.get(self.job.get_absolute_url())
        self.assertContains(response, reverse("jobs:photo", args=[self.photo.uuid]))
        self.assertContains(response, "Gutters before")

    def test_the_image_is_served_through_the_login_gated_view(self):
        """Never a public media path — that was unit 1's whole point."""
        body = self.client.get(self.job.get_absolute_url()).content.decode()
        self.assertNotIn("/media/private/", body)
        self.assertIn(reverse("jobs:photo", args=[self.photo.uuid]), body)

    def test_a_crew_member_on_another_job_sees_nothing_of_it(self):
        self.client.login(username="alex", password=PASSWORD)
        self.assertEqual(self.client.get(self.job.get_absolute_url()).status_code, 404)

    def test_the_estimate_page_shows_its_own_photos(self):
        self.client.login(username="boss", password=PASSWORD)
        self.add(
            url=reverse("jobs:quote_photo_add", args=[self.quote.pk]),
            kind=Photo.Kind.REFERENCE,
            caption="What they showed us",
        )
        response = self.client.get(self.quote.get_absolute_url())
        self.assertContains(response, "What they showed us")

    def test_the_job_page_does_not_ask_a_question_per_photo(self):
        for _ in range(4):
            self.add()
        url = self.job.get_absolute_url()
        with self.assertNumQueries(self.query_count(url)):
            self.client.get(url)

    def query_count(self, url):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            self.client.get(url)
        return len(captured.captured_queries)


class RemovingTests(PhotoTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="casey", password=PASSWORD)
        self.add()
        self.photo = Photo.objects.get()
        self.remove_url = reverse("jobs:photo_remove", args=[self.photo.uuid])

    def test_whoever_added_it_can_remove_it(self):
        self.client.post(self.remove_url)
        self.assertEqual(Photo.objects.count(), 0)

    def test_the_file_goes_with_the_row(self):
        """A stored photo of somebody's home is not a thing to keep."""
        storage, name = self.photo.image.storage, self.photo.image.name
        self.assertTrue(storage.exists(name))
        self.client.post(self.remove_url)
        self.assertFalse(storage.exists(name))

    def test_the_owner_can_remove_anybody_s_photo(self):
        self.client.login(username="boss", password=PASSWORD)
        self.client.post(self.remove_url)
        self.assertEqual(Photo.objects.count(), 0)

    def test_another_crew_member_on_the_job_cannot_remove_it(self):
        f.assign(self.job, self.alex)
        self.client.login(username="alex", password=PASSWORD)
        self.assertEqual(self.client.post(self.remove_url).status_code, 403)
        self.assertEqual(Photo.objects.count(), 1)

    def test_somebody_who_cannot_see_the_job_gets_not_found(self):
        # 404 before 403: they should not learn the photo exists.
        self.client.login(username="alex", password=PASSWORD)
        self.assertEqual(self.client.post(self.remove_url).status_code, 404)
        self.assertEqual(Photo.objects.count(), 1)

    def test_a_get_removes_nothing(self):
        self.assertIn(self.client.get(self.remove_url).status_code, (403, 405))
        self.assertEqual(Photo.objects.count(), 1)

    def test_removing_is_recorded_in_the_change_log(self):
        self.client.post(self.remove_url)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                content_type__model="photo", action=AuditLogEntry.Action.UPDATED
            ).exists()
        )

    def test_the_remove_button_shows_only_to_people_who_may_use_it(self):
        shown = self.client.get(self.job.get_absolute_url()).content.decode()
        self.assertIn(self.remove_url, shown)

        f.assign(self.job, self.alex)
        self.client.login(username="alex", password=PASSWORD)
        hidden = self.client.get(self.job.get_absolute_url()).content.decode()
        self.assertNotIn(self.remove_url, hidden)
