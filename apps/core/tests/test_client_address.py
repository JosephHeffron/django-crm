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

from apps.core.tests._caddy import CADDY, CADDY_ENV, adapt, answer_for, first_answer, strip_comments

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


def ports_setting(body):
    """A service's `ports` setting as written, or [] when it has none.

    The key line and every line under it, stripped. Compose accepts
    several spellings (a block list, an inline list, the long form
    with `target:` and `published:`), and a reader that understood
    only one would see nothing in the others and pass a public port
    (review of #208). Reading the raw lines means any spelling is seen,
    and the tests below accept exactly one.
    """
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^ {4}ports\s*:", line):
            setting = [line.strip()]
            for following in lines[i + 1 :]:
                if following.strip() and not following.startswith(" " * 5):
                    break
                if following.strip():
                    setting.append(following.strip())
            return setting
    return []


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
        self.assertEqual(ports_setting(caddy), [])

    def test_django_is_published_on_loopback_and_nowhere_else(self):
        # Exactly this spelling. Anything else, including a correct
        # binding written another way, fails and gets looked at.
        self.assertEqual(
            ports_setting(service(self.compose, "web")), ["ports:", '- "127.0.0.1:8000:8000"']
        )

    def test_the_database_is_not_published_at_all(self):
        self.assertEqual(ports_setting(service(self.compose, "db")), [])

    def test_only_caddy_is_on_the_host_network(self):
        # On the host network gunicorn would listen on every interface,
        # and PostgreSQL likewise, with no port mapping to stop them.
        for name in ("web", "db"):
            self.assertNotIn("network_mode", service(self.compose, name), name)

    def test_the_port_reader_sees_every_spelling(self):
        # The guards above are only as good as this.
        block = '    ports:\n      - "8000:8000"\n    image: x\n'
        inline = '    ports: ["5432:5432"]\n    image: x\n'
        long_form = "    ports:\n      - target: 8000\n        published: 8000\n    image: x\n"
        self.assertEqual(ports_setting(block), ["ports:", '- "8000:8000"'])
        self.assertEqual(ports_setting(inline), ['ports: ["5432:5432"]'])
        self.assertEqual(ports_setting(long_form), ["ports:", "- target: 8000", "published: 8000"])
        self.assertEqual(ports_setting("    image: x\n"), [])

    def test_the_crm_proxies_to_the_loopback_port(self):
        # A quick text check. The real one is
        # `test_crm_pages_are_answered_by_the_loopback_proxy`, which asks
        # the adapted config what actually answers a CRM page.
        live = strip_comments((ROOT / "Caddyfile").read_text())
        self.assertIn("reverse_proxy 127.0.0.1:8000", live)
        self.assertNotIn("web:8000", live, "web:8000 is only reachable on the compose network")

    def test_the_admin_api_is_off(self):
        live = strip_comments((ROOT / "Caddyfile").read_text()).strip()
        # Global options must be the first block in the file.
        self.assertTrue(live.startswith("{"), "the global options block is not first")
        first_block = live[: live.index("}") + 1]
        self.assertRegex(first_block, r"\badmin\s+off\b")


class AnswerReaderTests(SimpleTestCase):
    """`first_answer`, on hand-built routes, so it is proven able to see
    the failure the adapted-config tests look for."""

    PROXY = {"handler": "reverse_proxy", "upstreams": [{"dial": "127.0.0.1:8000"}]}

    def site(self, *catch_all):
        return [
            {
                "match": [{"host": ["crm.example.test"]}],
                "terminal": True,
                "handle": [
                    {
                        "handler": "subroute",
                        "routes": [
                            {"handle": [{"handler": "encode"}]},
                            {
                                "match": [{"path": ["/static/*"]}],
                                "handle": [{"handler": "file_server"}],
                            },
                            {"handle": [{"handler": "subroute", "routes": list(catch_all)}]},
                        ],
                    }
                ],
            }
        ]

    def test_a_page_reaches_the_proxy(self):
        routes = self.site({"handle": [self.PROXY]})
        self.assertIs(first_answer(routes, "crm.example.test", "/contacts/"), self.PROXY)
        self.assertEqual(
            first_answer(routes, "crm.example.test", "/static/x.css")["handler"], "file_server"
        )

    def test_an_answer_before_the_proxy_is_seen(self):
        respond = {"handler": "static_response", "status_code": 503}
        routes = self.site({"handle": [respond]}, {"handle": [self.PROXY]})
        self.assertIs(first_answer(routes, "crm.example.test", "/contacts/"), respond)

    def test_another_host_gets_nothing(self):
        routes = self.site({"handle": [self.PROXY]})
        self.assertIsNone(first_answer(routes, "elsewhere.test", "/contacts/"))


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

    def test_crm_pages_are_answered_by_the_loopback_proxy(self):
        # What actually answers, in the order Caddy runs things, so an
        # earlier `respond` or a misplaced handler fails here even when
        # a reverse_proxy with the right upstream exists somewhere.
        config = adapt(ROOT / "Caddyfile")
        for path in ("/", "/contacts/", "/accounts/login/", "/admin/login/"):
            with self.subTest(path=path):
                answer = answer_for(config, CADDY_ENV["CRM_HOST"], path)
                self.assertIsNotNone(answer, "nothing answers")
                self.assertEqual(answer.get("handler"), "reverse_proxy")
                self.assertEqual([u.get("dial") for u in answer["upstreams"]], ["127.0.0.1:8000"])

    def test_the_website_is_answered_from_files_not_django(self):
        config = adapt(ROOT / "Caddyfile")
        for host in (CADDY_ENV["WEBSITE_HOST"], CADDY_ENV["WEBSITE_WWW_HOST"]):
            with self.subTest(host=host):
                self.assertEqual(answer_for(config, host, "/").get("handler"), "file_server")

    def test_the_dev_stack_keeps_the_compose_network(self):
        # The deliberate difference recorded in Caddyfile.dev.
        proxies = handlers_of(adapt(ROOT / "Caddyfile.dev"), "reverse_proxy")
        self.assertTrue(proxies)
        for proxy in proxies:
            dials = [upstream.get("dial") for upstream in proxy.get("upstreams", [])]
            self.assertEqual(dials, ["web:8000"])
