import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Photo
from apps.users.models import get_profile
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"


def image(name="shot.jpg"):
    out = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(out, format="JPEG")
    return SimpleUploadedFile(name, out.getvalue(), content_type="image/jpeg")


class MediaTestCase(TestCase):
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
        self.photo = Photo.objects.create(
            job=self.job, kind=Photo.Kind.BEFORE, image=image(), uploaded_by=self.owner
        )
        self.url = reverse("jobs:photo", args=[self.photo.uuid])


class PhotoAccessTests(MediaTestCase):
    def test_a_signed_out_visitor_is_sent_to_sign_in(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_the_crew_member_on_the_job_sees_it(self):
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content)[:2], b"\xff\xd8")  # a JPEG

    def test_a_crew_member_on_a_different_job_is_not_found(self):
        # 404, never 403: a 403 would confirm the photo exists.
        self.client.login(username="alex", password=PASSWORD)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_the_owner_sees_any_photo(self):
        self.client.login(username="boss", password=PASSWORD)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_someone_with_no_role_is_refused(self):
        f.user("nobody")
        self.client.login(username="nobody", password=PASSWORD)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_an_unknown_photo_is_not_found(self):
        self.client.login(username="boss", password=PASSWORD)
        unknown = reverse("jobs:photo", args=["00000000-0000-0000-0000-000000000000"])
        self.assertEqual(self.client.get(unknown).status_code, 404)

    def test_a_row_whose_file_has_gone_says_not_found(self):
        self.client.login(username="boss", password=PASSWORD)
        self.photo.image.storage.delete(self.photo.image.name)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_an_estimate_photo_follows_the_estimate(self):
        quote = f.quote(self.customer, self.owner)
        photo = Photo.objects.create(
            quote=quote, kind=Photo.Kind.REFERENCE, image=image(), uploaded_by=self.owner
        )
        url = reverse("jobs:photo", args=[photo.uuid])
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.get(url).status_code, 404)  # crew don't see estimates
        self.client.login(username="boss", password=PASSWORD)
        self.assertEqual(self.client.get(url).status_code, 200)


class PhotoHeaderTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="boss", password=PASSWORD)

    def test_it_is_shown_not_run_and_not_cached_by_anyone_else(self):
        response = self.client.get(self.url)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("inline", response["Content-Disposition"])
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_the_stored_name_is_never_the_uploaded_one(self):
        # An uploaded filename can carry a customer's name or address.
        photo = Photo.objects.create(
            job=self.job,
            kind=Photo.Kind.AFTER,
            image=image("the smiths at 12 oak ave.jpg"),
            uploaded_by=self.owner,
        )
        self.assertNotIn("smith", photo.image.name.lower())
        self.assertIn(str(photo.uuid), photo.image.name)
        self.assertTrue(photo.image.name.startswith("private/"))


class AvatarTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        profile = get_profile(self.casey)
        profile.photo = image("casey.jpg")
        profile.save()
        self.url = reverse("people:avatar", args=["casey"])

    def test_a_signed_out_visitor_is_sent_to_sign_in(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_a_teammate_sees_it(self):
        self.client.login(username="alex", password=PASSWORD)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_someone_with_no_role_is_refused(self):
        f.user("nobody")
        self.client.login(username="nobody", password=PASSWORD)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_somebody_with_no_picture_is_not_found(self):
        self.client.login(username="boss", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("people:avatar", args=["alex"])).status_code, 404)

    def test_the_file_is_stored_privately(self):
        self.assertTrue(get_profile(self.casey).photo.name.startswith("private/avatars/"))


class ProxyConfigTests(TestCase):
    """The web server must not serve these files from disk — that's what
    this whole view exists to prevent."""

    def test_both_caddyfiles_refuse_private_media(self):
        for name in ("Caddyfile", "Caddyfile.dev"):
            with open(name) as handle:
                config = handle.read()
            self.assertIn("/media/private/*", config, name)
            self.assertIn("respond @private 404", config, name)
