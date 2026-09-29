import importlib
import json
import os
import re
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core import pwa
from apps.crm.tests._helpers import grant_role

User = get_user_model()


class ManifestTests(TestCase):
    def test_manifest_is_public_json_with_installable_fields(self):
        response = self.client.get(reverse("core:manifest"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/manifest+json")
        data = json.loads(response.content)
        self.assertEqual(data["name"], "Exterior CRM")
        self.assertEqual(data["display"], "standalone")
        self.assertEqual(data["start_url"], "/")
        sizes = {icon["sizes"] for icon in data["icons"]}
        self.assertTrue({"192x192", "512x512"} <= sizes)
        self.assertTrue(any(icon.get("purpose") == "maskable" for icon in data["icons"]))

    @override_settings(CRM_BRAND_NAME="Sparkle Exteriors", CRM_BRAND_SHORT_NAME="Sparkle")
    def test_manifest_uses_the_configured_brand(self):
        data = json.loads(self.client.get(reverse("core:manifest")).content)
        self.assertEqual((data["name"], data["short_name"]), ("Sparkle Exteriors", "Sparkle"))

    def test_every_manifest_icon_exists(self):
        # The test client doesn't serve static files, so check the files
        # themselves are findable by staticfiles (what collectstatic uses).
        for icon in pwa.manifest()["icons"]:
            path = icon["src"].removeprefix(settings.STATIC_URL)
            self.assertIsNotNone(finders.find(path), path)


class ServiceWorkerTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("core:service_worker"))
        self.body = self.response.content.decode()

    def test_served_publicly_from_root_as_javascript_without_caching(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertEqual(self.response["Content-Type"], "application/javascript")
        self.assertEqual(self.response["Cache-Control"], "no-cache")

    def test_precaches_the_shell_and_offline_page(self):
        precache = json.loads(re.search(r"const PRECACHE = (\[.*?\]);", self.body)[1])
        self.assertEqual(precache, pwa.precache_urls())
        self.assertIn(f'const OFFLINE_URL = "{reverse("core:offline")}"', self.body)
        for path in pwa.PRECACHE_STATIC:
            self.assertIsNotNone(finders.find(path), path)

    def test_never_caches_navigations(self):
        # Pages (which hold customer data) are only ever fetched from the
        # network; the offline page is the sole navigation fallback.
        self.assertIn("fetch(request).catch(() => caches.match(OFFLINE_URL))", self.body)

    def test_output_is_not_html_escaped(self):
        self.assertNotIn("&quot;", self.body)


class AssetVersionTests(TestCase):
    def test_version_is_a_stable_content_hash(self):
        self.assertRegex(pwa.asset_version(), r"^[0-9a-f]{16}$")
        self.assertEqual(pwa.asset_version(), pwa.asset_version())

    def test_brand_change_rolls_the_cache(self):
        before = pwa._compute_asset_version()
        with override_settings(CRM_BRAND_NAME="Something Else"):
            self.assertNotEqual(pwa._compute_asset_version(), before)


class OfflinePageTests(TestCase):
    def test_offline_page_is_public_and_standalone(self):
        response = self.client.get(reverse("core:offline"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You're offline")
        self.assertNotContains(response, 'class="sidebar"')


class PageHeadTests(TestCase):
    def test_pages_link_the_manifest_and_register_the_worker(self):
        grant_role(User.objects.create_user("alice", password="correct-horse-battery"))
        self.client.login(username="alice", password="correct-horse-battery")
        response = self.client.get("/")
        self.assertContains(response, f'<link rel="manifest" href="{reverse("core:manifest")}">')
        self.assertContains(response, f'data-sw="{reverse("core:service_worker")}"')


class ProductionCspAllowsThePwaTests(TestCase):
    """default-src 'none' would otherwise block the manifest and the
    service worker in production."""

    def test_manifest_and_worker_sources_allowed(self):
        env = {
            "DJANGO_ALLOWED_HOSTS": "crm.example.com",
            "DJANGO_SECRET_KEY": "x" * 60,
        }
        with mock.patch.dict(os.environ, env):
            production = importlib.import_module("config.settings.production")
            production = importlib.reload(production)
        self.assertEqual(production.SECURE_CSP["manifest-src"], ["'self'"])
        self.assertEqual(production.SECURE_CSP["worker-src"], ["'self'"])
        self.assertEqual(production.SECURE_CSP["default-src"], ["'none'"])
