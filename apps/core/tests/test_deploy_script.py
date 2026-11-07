"""A full deploy is healthy only if Caddy is serving both sites.

`scripts/deploy.sh` used to call a deploy good once Podman reported the
`db` and `web` containers healthy. Caddy was never asked. A Caddyfile
it rejects (an unset `CRM_HOST` or `WEBSITE_HOST`, a syntax error)
stops Caddy and takes both sites offline while `db` and `web` stay
healthy, so that deploy would have been recorded as a success.

Now the deploy also fetches the CRM's `/health/` and the website's home
page through Caddy on the host, certificate checked, and rolls back if
either fails. These tests run the real script in throwaway repositories
(apps/core/tests/_deploy.py) with the container tools and curl stubbed.

Also here: `systemd/crm.service` must find a podman-compose installed
by pipx, because Ubuntu 24.04's own package (1.0.6) ignores the
`depends_on` health conditions the stack relies on; those arrived in
podman-compose 1.3.0.
"""

from pathlib import Path
from unittest import skipIf

from django.conf import settings
from django.test import SimpleTestCase

from apps.core.tests._deploy import GIT, GOOD_PAGE, DeployHarness, skips_certificate_checks

ROOT = Path(settings.BASE_DIR)


@skipIf(not GIT, "needs git")
class FullDeployTests(DeployHarness, SimpleTestCase):
    def test_a_healthy_deploy_checks_both_sites_through_caddy(self):
        target = self.push("code", {"apps/app.py": "VALUE = 2\n"})
        result = self.deploy("main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.head(), target)
        self.assertEqual(self.state(), self.deployed)
        curl = self.log("curl")
        self.assertIn("--resolve crm.example.test:443:127.0.0.1", curl)
        self.assertIn("https://crm.example.test/health/", curl)
        self.assertIn("https://example.test/", curl)
        self.assertFalse(skips_certificate_checks(curl), "the certificate must be checked")
        self.assertIn("CRM healthy through Caddy", result.stdout)
        self.assertIn("website healthy", result.stdout)

    def test_the_stack_is_rebuilt_and_recreated(self):
        self.push("code", {"apps/app.py": "VALUE = 3\n"})
        self.deploy("main")
        containers = self.log("containers")
        for call in ("build web", "pull db caddy", "down", "up -d"):
            self.assertIn(call, containers)

    def test_caddy_down_rolls_back(self):
        self.push("code", {"apps/app.py": "VALUE = 4\n"})
        result = self.deploy("main", STUB_CURL_FAIL="1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(self.head(), self.deployed, "not rolled back")
        self.assertIsNone(self.state(), "a failed deploy was recorded as good")
        self.assertIn("Caddy is not serving", result.stdout)
        # Caddy is down for the old revision too, so the rollback is
        # reported as failing rather than as a recovery.
        self.assertIn("ALSO failed", result.stderr)

    def test_a_crm_that_answers_badly_rolls_back(self):
        self.push("code", {"apps/app.py": "VALUE = 5\n"})
        result = self.deploy("main", STUB_CRM_DOWN="1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.head(), self.deployed)
        self.assertIn("CRM not reachable through Caddy", result.stdout)

    def test_a_broken_website_in_a_full_deploy_rolls_back_and_recovers(self):
        self.push(
            "both", {"apps/app.py": "VALUE = 6\n", "website/index.html": "<main>no header</main>\n"}
        )
        result = self.deploy("main")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.head(), self.deployed)
        self.assertIn("Rolled back", result.stderr)
        self.assertEqual((self.server / "website/index.html").read_text(), GOOD_PAGE)

    def test_a_missing_crm_host_fails_rather_than_passing(self):
        (self.server / ".env").write_text("WEBSITE_HOST=example.test\n")
        self.push("code", {"apps/app.py": "VALUE = 7\n"})
        result = self.deploy("main")
        self.assertEqual(result.returncode, 1)
        self.assertIn("CRM_HOST is not set", result.stderr)

    def test_unhealthy_containers_are_caught_before_caddy_is_asked(self):
        self.push("code", {"apps/app.py": "VALUE = 8\n"})
        result = self.deploy("main", STUB_HEALTH="unhealthy")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.head(), self.deployed)
        self.assertNotIn("/health/", self.log("curl"))


@skipIf(not GIT, "needs git")
class StatusTests(DeployHarness, SimpleTestCase):
    def test_status_reports_both_sites(self):
        result = self.deploy("status")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("healthy: db and web", result.stdout)
        self.assertIn("CRM healthy through Caddy", result.stdout)
        self.assertIn("website healthy", result.stdout)

    def test_status_fails_when_caddy_is_down(self):
        result = self.deploy("status", STUB_CURL_FAIL="1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("CRM not reachable through Caddy", result.stdout)
        self.assertIn("website not serving", result.stdout)


class CertificateCheckReaderTests(SimpleTestCase):
    def test_it_sees_every_spelling(self):
        for call in (
            "-k https://x/",
            "-kfsS https://x/",
            "-fsSk https://x/",
            "--insecure https://x/",
        ):
            self.assertTrue(skips_certificate_checks(call), call)
        self.assertFalse(skips_certificate_checks("-fsS --max-time 15 https://x/"))


class CrmServiceTests(SimpleTestCase):
    def setUp(self):
        self.unit = (ROOT / "systemd" / "crm.service").read_text()
        self.directives = [
            line.strip() for line in self.unit.splitlines() if not line.lstrip().startswith("#")
        ]

    def test_podman_compose_is_found_on_a_path_that_includes_pipx(self):
        self.assertIn(
            "ExecStart=/usr/bin/env podman-compose -f compose.prod.yml up -d", self.directives
        )
        self.assertIn(
            "ExecStop=/usr/bin/env podman-compose -f compose.prod.yml down", self.directives
        )
        path = next(d for d in self.directives if d.startswith("Environment=PATH="))
        entries = path.split("=", 2)[2].split(":")
        self.assertEqual(entries[0], "%h/.local/bin", "pipx's directory must be searched first")
        self.assertIn("/usr/bin", entries)

    def test_no_hardcoded_podman_compose_path_remains(self):
        self.assertNotIn("/usr/bin/podman-compose", "\n".join(self.directives))
