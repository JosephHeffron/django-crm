"""Production Caddy sees every visitor's real address (ADR 0022).

Under rootless Podman, a port published on a compose network is
forwarded by `rootlessport`, which rewrites the source of every
connection. With Caddy behind it, every visitor arrived from one
internal address, and the per-IP login limit (ADR 0020) became one
bucket for the whole internet: ten wrong passwords from anyone locked
out everyone.

So Caddy runs on the host network, and Django is published on the
loopback address only. These tests hold the three things that layout
depends on: Caddy on the host network, Django on loopback and nowhere
else, and Caddy's admin API off, because on the host network it would
listen on the server's own loopback.

The compose file is read as text (the project has no YAML parser) and
the Caddyfile through `caddy adapt` where the binary exists. The proof
that addresses really arrive intact is on the droplet:
docs/ADMIN_GUIDE.md has the check.
"""

import re
from pathlib import Path
from unittest import skipIf

from django.conf import settings
from django.test import SimpleTestCase

from apps.core.tests._caddy import CADDY, adapt, strip_comments

ROOT = Path(settings.BASE_DIR)


def service(compose, name):
    """One service's lines from a compose file, comments dropped.

    A service is a two-space-indented key under `services:`; its body
    is everything indented further, up to the next key at two spaces or
    less.
    """
    lines = compose.splitlines()
    start = lines.index(f"  {name}:")
    body = []
    for line in lines[start + 1 :]:
        if re.match(r"^ {0,2}\S", line):
            break
        if not line.strip().startswith("#"):
            body.append(line)
    return "\n".join(body)


def published_ports(body):
    """The entries of a service's `ports:` list."""
    match = re.search(r"^ {4}ports:\n((?: {6}- .*\n?)+)", body, re.MULTILINE)
    if not match:
        return []
    return [line.strip()[2:].strip().strip("\"'") for line in match.group(1).splitlines()]


def handlers_of(config, kind):
    """Every handler of one kind, anywhere in an adapted config."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("handler") == kind:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(config)
    return found


class ProductionNetworkTests(SimpleTestCase):
    def setUp(self):
        self.compose = (ROOT / "compose.prod.yml").read_text()

    def test_caddy_is_on_the_host_network(self):
        caddy = service(self.compose, "caddy")
        self.assertRegex(caddy, r"(?m)^ {4}network_mode: host$")
        # Ports do not apply on the host network; one left here would
        # suggest Caddy is still behind the port forwarder.
        self.assertEqual(published_ports(caddy), [])

    def test_django_is_published_on_loopback_and_nowhere_else(self):
        self.assertEqual(published_ports(service(self.compose, "web")), ["127.0.0.1:8000:8000"])

    def test_the_database_is_not_published_at_all(self):
        self.assertEqual(published_ports(service(self.compose, "db")), [])

    def test_the_port_reader_sees_a_public_binding(self):
        # The guard above is only as good as this.
        body = '    ports:\n      - "8000:8000"\n      - "127.0.0.1:9000:9000"\n'
        self.assertEqual(published_ports(body), ["8000:8000", "127.0.0.1:9000:9000"])
        self.assertEqual(published_ports("    image: x\n"), [])

    def test_the_crm_proxies_to_the_loopback_port(self):
        live = strip_comments((ROOT / "Caddyfile").read_text())
        self.assertIn("reverse_proxy 127.0.0.1:8000", live)
        self.assertNotIn("web:8000", live, "web:8000 is only reachable on the compose network")

    def test_the_admin_api_is_off(self):
        live = strip_comments((ROOT / "Caddyfile").read_text()).strip()
        # Global options must be the first block in the file.
        self.assertTrue(live.startswith("{"), "the global options block is not first")
        first_block = live[: live.index("}") + 1]
        self.assertRegex(first_block, r"\badmin\s+off\b")


@skipIf(not CADDY, "needs the caddy binary; CI installs it")
class AdaptedProductionConfigTests(SimpleTestCase):
    """The same properties, read from the configuration Caddy will run."""

    def test_the_admin_api_is_disabled(self):
        self.assertIs(adapt(ROOT / "Caddyfile").get("admin", {}).get("disabled"), True)

    def test_every_proxy_upstream_is_the_loopback_port(self):
        proxies = handlers_of(adapt(ROOT / "Caddyfile"), "reverse_proxy")
        self.assertTrue(proxies, "no reverse_proxy at all — the CRM would not be served")
        for proxy in proxies:
            dials = [upstream.get("dial") for upstream in proxy.get("upstreams", [])]
            self.assertEqual(dials, ["127.0.0.1:8000"])

    def test_the_dev_stack_keeps_the_compose_network(self):
        # The deliberate difference recorded in Caddyfile.dev.
        proxies = handlers_of(adapt(ROOT / "Caddyfile.dev"), "reverse_proxy")
        self.assertTrue(proxies)
        for proxy in proxies:
            dials = [upstream.get("dial") for upstream in proxy.get("upstreams", [])]
            self.assertEqual(dials, ["web:8000"])
