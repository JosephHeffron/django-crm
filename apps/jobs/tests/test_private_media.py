import io
import json
import os
import shutil
import subprocess
import tempfile
from unittest import mock, skipIf

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


JPEG_MAGIC = b"\xff\xd8"


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

    def assertSentTheImage(self, response):
        """A 200 on its own would pass for an empty body."""
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content)
        self.assertTrue(body, "the response had no body")
        self.assertEqual(body[:2], JPEG_MAGIC, "the body was not a JPEG")

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
        self.assertSentTheImage(self.client.get(self.url))

    def test_a_crew_member_on_a_different_job_is_not_found(self):
        # 404, never 403: a 403 would confirm the photo exists.
        self.client.login(username="alex", password=PASSWORD)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_the_owner_sees_any_photo(self):
        self.client.login(username="boss", password=PASSWORD)
        self.assertSentTheImage(self.client.get(self.url))

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
        self.assertSentTheImage(self.client.get(url))


class StorageFailureTests(MediaTestCase):
    """A broken media volume must not look like a missing photo."""

    def setUp(self):
        super().setUp()
        self.client.login(username="boss", password=PASSWORD)

    def test_a_file_that_is_gone_is_not_found(self):
        self.photo.image.storage.delete(self.photo.image.name)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_a_permission_error_is_not_dressed_up_as_not_found(self):
        # Otherwise an unreadable media volume reads, to everyone, as
        # "the photos were never uploaded", and nothing says otherwise.
        def refuse(*args, **kwargs):
            raise PermissionError(13, "Permission denied")

        with mock.patch.object(Photo.image.field.storage, "open", refuse):
            with self.assertRaises(PermissionError):
                self.client.get(self.url)

    def test_a_read_error_is_not_dressed_up_as_not_found(self):
        def fail(*args, **kwargs):
            raise OSError(5, "Input/output error")

        with mock.patch.object(Photo.image.field.storage, "open", fail):
            with self.assertRaises(OSError):
                self.client.get(self.url)


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

    def test_the_browser_is_told_it_is_an_image(self):
        """`nosniff` means the type we send is the type that's used.

        Nothing passes a content type explicitly — FileResponse guesses
        it from the stored filename — so this asserts the guess comes
        out right. If it ever became application/octet-stream, every
        photo would download instead of displaying.
        """
        self.assertEqual(self.client.get(self.url)["Content-Type"], "image/jpeg")

    def test_an_avatar_is_also_served_as_an_image(self):
        profile = get_profile(self.casey)
        profile.photo = image("casey.jpg")
        profile.save()
        response = self.client.get(reverse("people:avatar", args=["casey"]))
        self.assertEqual(response["Content-Type"], "image/jpeg")

    def test_the_length_is_sent_so_a_short_body_is_detectable(self):
        # FileResponse streams; a read error partway through truncates
        # the body rather than becoming a 500. Content-Length is what
        # lets the client notice.
        response = self.client.get(self.url)
        self.assertEqual(int(response["Content-Length"]), len(b"".join(response.streaming_content)))

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
        self.assertSentTheImage(self.client.get(self.url))

    def test_someone_with_no_role_is_refused(self):
        f.user("nobody")
        self.client.login(username="nobody", password=PASSWORD)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_somebody_with_no_picture_is_not_found(self):
        self.client.login(username="boss", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("people:avatar", args=["alex"])).status_code, 404)

    def test_the_file_is_stored_privately(self):
        self.assertTrue(get_profile(self.casey).photo.name.startswith("private/avatars/"))


def strip_comments(config):
    """A Caddyfile comment runs from an unquoted `#` to end of line.

    Commented-out text is not configuration, and a test that cannot
    tell the difference will pass against a disabled handler.
    """
    out = []
    for line in config.splitlines():
        quoted = False
        for i, char in enumerate(line):
            if char == '"':
                quoted = not quoted
            elif char == "#" and not quoted:
                line = line[:i]
                break
        out.append(line)
    return "\n".join(out)


def adapted_routes(name):
    """The path matchers of `name`, in the order Caddy will try them.

    `caddy adapt` is the config Caddy actually runs. Reading the file
    instead means reading intent, and the two came apart once already:
    the first version of this guard passed while every private photo
    was being served (logs/claude/phase-18-unit1-private-media.md).
    """
    raw = subprocess.run(
        ["caddy", "adapt", "--config", name],
        capture_output=True,
        text=True,
        check=True,
        # The production file takes the hostname from the same variable
        # Django uses; any value adapts the same.
        env={**os.environ, "DJANGO_ALLOWED_HOSTS": "example.test"},
    ).stdout
    servers = json.loads(raw)["apps"]["http"]["servers"]
    routes = []

    def walk(node):
        paths = [path for match in node.get("match", []) for path in match.get("path", [])]
        handlers = []

        def collect(handles):
            for handle in handles:
                kind = handle.get("handler")
                if kind == "subroute":
                    for route in handle.get("routes", []):
                        if route.get("match"):
                            walk(route)
                        else:
                            collect(route.get("handle", []))
                else:
                    handlers.append(kind)

        collect(node.get("handle", []))
        if paths:
            routes.append((paths, handlers))

    for server in servers.values():
        for route in server.get("routes", []):
            walk(route)
    return routes


CADDY = shutil.which("caddy")


class ProxyConfigTests(TestCase):
    """The web server must not serve these files from disk — that's what
    this whole view exists to prevent, so a config change that undid it
    has to fail here rather than only in production.

    Two earlier versions of this test were worthless, both for the same
    reason: they searched the file's text. The first checked that
    `/media/private/*` and a `respond 404` appeared somewhere, and
    passed against a config that served every private photo with a 200.
    Text also cannot tell a live directive from a commented-out one.

    So the real assertions run `caddy adapt` and read the configuration
    Caddy will actually use. Note what that revealed: Caddy orders
    `handle_path` blocks by how specific their path is, not by where
    they appear in the file — `/media/private/*` sorts ahead of
    `/media/*` even when written after it. Where they sit in the file
    is therefore not the thing to assert.
    """

    CONFIGS = ("Caddyfile", "Caddyfile.dev")

    def read(self, name):
        with open(name) as handle:
            return handle.read()

    # --- the configuration Caddy will actually run -------------------

    @skipIf(not CADDY, "needs the caddy binary; CI installs it")
    def test_private_media_is_refused_before_anything_serves_it(self):
        for name in self.CONFIGS:
            routes = adapted_routes(name)
            private = [i for i, (paths, _) in enumerate(routes) if "/media/private/*" in paths]
            serving = [
                i
                for i, (paths, handlers) in enumerate(routes)
                if "file_server" in handlers and any(p.startswith("/media") for p in paths)
            ]
            self.assertTrue(private, f"{name}: nothing matches /media/private/* in the live config")
            self.assertTrue(serving, f"{name}: expected a /media/* file_server to exist")
            self.assertLess(
                max(private),
                min(serving),
                f"{name}: a file_server for /media/* is reached before the private "
                "path is refused, so private photos are served from disk",
            )

    @skipIf(not CADDY, "needs the caddy binary; CI installs it")
    def test_the_private_route_answers_and_never_reads_the_disk(self):
        for name in self.CONFIGS:
            for paths, handlers in adapted_routes(name):
                if "/media/private/*" in paths:
                    self.assertIn("static_response", handlers, f"{name}: {handlers}")
                    self.assertNotIn("file_server", handlers, name)
                    self.assertNotIn("reverse_proxy", handlers, name)

    @skipIf(not CADDY, "needs the caddy binary; CI installs it")
    def test_the_configs_are_valid(self):
        # An invalid file would make every other assertion here vacuous.
        for name in self.CONFIGS:
            result = subprocess.run(
                ["caddy", "validate", "--config", name],
                capture_output=True,
                text=True,
                env={**os.environ, "DJANGO_ALLOWED_HOSTS": "example.test"},
            )
            self.assertEqual(result.returncode, 0, f"{name}: {result.stderr[-400:]}")

    # --- a weaker guard that needs no binary -------------------------

    def test_a_live_private_handler_is_present_in_both_files(self):
        """Comment-blind, so commenting the block out fails here too."""
        for name in self.CONFIGS:
            config = strip_comments(self.read(name))
            self.assertIn(
                "handle_path /media/private/*",
                config,
                f"{name}: no live `handle_path /media/private/*` block — a commented-out "
                "one does not count, and a `respond` matcher sorts after handle_path "
                "and never fires",
            )
            start = config.index("handle_path /media/private/*")
            block = config[start : config.index("}", start)]
            self.assertIn("respond 404", block, name)
            self.assertNotIn("file_server", block, name)

    def test_caddy_is_installed_wherever_this_suite_gates_a_merge(self):
        """Skipping the real guards is how this control was lost once.

        CI installs the binary (.github/workflows/ci.yml). If that step
        ever stops working, this says so instead of the assertions above
        quietly skipping.
        """
        if os.environ.get("CI"):
            self.assertTrue(CADDY, "CI must install caddy or the proxy guards do not run")

    def test_strip_comments_removes_commented_directives(self):
        # The guard above is only as good as this.
        self.assertEqual(strip_comments("# handle_path /x {").strip(), "")
        self.assertEqual(strip_comments('respond "a#b" # tail').strip(), 'respond "a#b"')
