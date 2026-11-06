"""The public website in website/ (ADRs 0016 and 0017).

This repository is public, and anything in website/ is published as
soon as it is committed, so most of these tests guard what may go in
that folder. The rest keep the pages and the shared partials
consistent, and check what Caddy will actually do for the website
hostnames.

Each guard here has a test that feeds it a known-bad input. A guard
nobody has seen fail can be vacuous, and this project has shipped
vacuous guards before (logs/claude/phase-18-unit1-private-media.md).
"""

import io
import re
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from unittest import skipIf
from urllib.parse import urlsplit
from xml.etree import ElementTree

from django.conf import settings
from django.test import SimpleTestCase
from PIL import ExifTags, Image

from apps.core.tests._caddy import CADDY, CADDY_ENV, adapt

ROOT = Path(settings.BASE_DIR)
WEBSITE = ROOT / "website"
PARTIALS = WEBSITE / "partials"

# Where the site will live once the apex moves. Canonical URLs, the
# sitemap and robots.txt name it; the preview hostname is not indexed
# as the site's address because every page's canonical points here.
SITE_ORIGIN = "https://heffronexteriorservices.com"

# ADR 0017. Anything else — a .csv of customers, a .pdf invoice, an
# .sql dump, a stray .env, a .md note — fails, because whatever lands
# in website/ is served to the public by Caddy.
ALLOWED_SUFFIXES = {
    ".html",
    ".css",
    ".js",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".woff2",
    ".ico",
    ".txt",
    ".xml",
    ".webmanifest",
}
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_BYTES = 1024 * 1024

# The only template action a page may contain. Caddy's `templates`
# directive can read environment variables, and the Caddy container is
# given the whole .env — so `{{env "DJANGO_SECRET_KEY"}}` in a page
# would publish the key (ADR 0016).
INCLUDE = re.compile(r'\{\{\s*include\s+"(/partials/[a-z0-9-]+\.html)"\s*\}\}')

# Paths on the website hostnames that may reach Django. Empty until
# Phase 22.5 unit 5 adds exactly "/book/*".
ALLOWED_PROXY_PATHS = set()

EXTERNAL = ("http://", "https://", "mailto:", "tel:")


# --- what is in the folder ------------------------------------------


def website_files():
    return sorted(path for path in WEBSITE.rglob("*") if path.is_file())


def pages():
    """Every HTML document a visitor can be served as a page."""
    return sorted(WEBSITE.glob("*.html"))


def indexable_pages():
    return [page for page in pages() if page.name != "404.html"]


def partials():
    return sorted(PARTIALS.glob("*.html"))


def clean_path(page):
    """The URL a page is linked and indexed under: /services, not /services.html."""
    return "/" if page.name == "index.html" else f"/{page.stem}"


def served_file(path):
    """The file Caddy serves for a site path, or None.

    Mirrors the website block: /partials/ is refused, then
    `try_files {path} {path}.html`, and a directory serves its
    index.html.
    """
    if path.startswith("/partials/"):
        return None
    relative = path.lstrip("/")
    target = (WEBSITE / relative).resolve()
    if not target.is_relative_to(WEBSITE.resolve()):
        return None
    if path.endswith("/"):
        index = target / "index.html"
        return index if index.is_file() else None
    if target.is_file():
        return target
    html = WEBSITE / f"{relative}.html"
    return html if html.is_file() else None


def rendered(page):
    """A page as Caddy's `templates` serves it, with its includes inlined."""
    return INCLUDE.sub(
        lambda match: (WEBSITE / match.group(1).lstrip("/")).read_text(),
        page.read_text(),
    )


def stray_template_syntax(text, markers=("{{", "}}")):
    """Template syntax left over once the allowed includes are removed."""
    remainder = INCLUDE.sub("", text)
    return [marker for marker in markers if marker in remainder]


def image_metadata(path):
    """The metadata blocks an image carries; empty means clean."""
    with Image.open(path) as image:
        found = []
        if image.getexif() or "exif" in image.info:
            found.append("EXIF")
        if any("xmp" in str(key).lower() for key in image.info):
            found.append("XMP")
        return found


class Document(HTMLParser):
    """The parts of a page these tests look at."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.title = ""
        self._in_title = False
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data

    def all(self, tag):
        return [attrs for name, attrs in self.elements if name == tag]

    def meta(self, key, value):
        return [attrs.get("content") for attrs in self.all("meta") if attrs.get(key) == value]

    def ids(self):
        return {attrs["id"] for _, attrs in self.elements if attrs.get("id")}

    def urls(self):
        for _, attrs in self.elements:
            for name in ("href", "src"):
                if attrs.get(name):
                    yield attrs[name]
            for candidate in (attrs.get("srcset") or "").split(","):
                if candidate.strip():
                    yield candidate.split()[0]


# --- the private-data guard (ADR 0017) ------------------------------


class WebsiteContentGuardTests(SimpleTestCase):
    def test_the_folder_has_pages_to_check(self):
        # Every loop below passes on an empty folder; this one does not.
        self.assertTrue(WEBSITE.is_dir())
        self.assertIn(WEBSITE / "index.html", pages())
        self.assertTrue(partials())

    def test_only_allow_listed_file_types(self):
        for path in website_files():
            self.assertIn(
                path.suffix.lower(),
                ALLOWED_SUFFIXES,
                f"{path.relative_to(ROOT)} is not a web asset. Everything in website/ is "
                "published; customer data, documents and notes never go there (ADR 0017).",
            )

    def test_no_file_is_over_the_size_cap(self):
        for path in website_files():
            self.assertLessEqual(
                path.stat().st_size,
                MAX_BYTES,
                f"{path.relative_to(ROOT)} is over 1 MiB. Resize photos to a 2000px long "
                "edge first; docs/WEBSITE.md has the command.",
            )

    def test_no_image_carries_metadata(self):
        for path in website_files():
            if path.suffix.lower() in RASTER_SUFFIXES:
                self.assertEqual(
                    image_metadata(path),
                    [],
                    f"{path.relative_to(ROOT)} carries metadata. A phone photo's EXIF holds "
                    "the GPS position it was taken at — a customer's address. Strip it "
                    "before committing; docs/WEBSITE.md has the command.",
                )

    def test_svgs_carry_no_script(self):
        script = re.compile(r"<script|\son[a-z]+\s*=|javascript:", re.IGNORECASE)
        for path in website_files():
            if path.suffix.lower() == ".svg":
                self.assertIsNone(script.search(path.read_text()), path.relative_to(ROOT))

    def test_nothing_lives_under_media(self):
        # The private-media guard checks every /media/* file server in
        # every site block; website images go under /assets/ (ADR 0016).
        self.assertFalse((WEBSITE / "media").exists())

    # --- the guards themselves can fail -----------------------------

    def test_the_metadata_check_catches_a_gps_tagged_photo(self):
        exif = Image.Exif()
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        gps[ExifTags.GPS.GPSLatitudeRef] = "N"
        gps[ExifTags.GPS.GPSLatitude] = (39.0, 6.0, 0.0)
        with tempfile.TemporaryDirectory() as folder:
            tagged = Path(folder) / "tagged.jpg"
            clean = Path(folder) / "clean.jpg"
            Image.new("RGB", (8, 8)).save(tagged, "JPEG", exif=exif)
            Image.new("RGB", (8, 8)).save(clean, "JPEG")
            self.assertEqual(image_metadata(tagged), ["EXIF"])
            self.assertEqual(image_metadata(clean), [])

    def test_the_metadata_check_catches_xmp(self):
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8)).save(buffer, "JPEG", xmp=b"<x:xmpmeta/>")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "xmp.jpg"
            path.write_bytes(buffer.getvalue())
            self.assertIn("XMP", image_metadata(path))


# --- shared partials and template syntax (ADRs 0016, 0017) ----------


class WebsiteTemplateTests(SimpleTestCase):
    def test_partials_contain_no_template_syntax(self):
        # Caddy's templates read them now and Django will in unit 5; the
        # day one carries either engine's syntax, one rendering breaks.
        for partial in partials():
            text = partial.read_text()
            for marker in ("{{", "{%", "{#"):
                self.assertNotIn(marker, text, f"{partial.relative_to(ROOT)} contains {marker}")

    def test_a_page_may_only_include_partials(self):
        for page in pages():
            self.assertEqual(
                stray_template_syntax(page.read_text()),
                [],
                f"{page.relative_to(ROOT)}: the only template action allowed in a page is "
                '{{include "/partials/…"}} — `templates` can read the server\'s environment',
            )

    def test_the_template_check_catches_a_leak(self):
        self.assertEqual(stray_template_syntax('{{include "/partials/header.html"}}'), [])
        self.assertEqual(stray_template_syntax('<p>{{env "DJANGO_SECRET_KEY"}}</p>'), ["{{", "}}"])
        self.assertTrue(stray_template_syntax('{{ include "/etc/passwd" }}'))
        self.assertTrue(stray_template_syntax('{{- include "/partials/header.html" -}}'))

    def test_every_include_names_a_partial_that_exists(self):
        for page in pages():
            for name in INCLUDE.findall(page.read_text()):
                self.assertTrue((WEBSITE / name.lstrip("/")).is_file(), f"{page.name}: {name}")

    def test_every_page_has_the_shared_header_and_footer_once(self):
        for page in pages():
            included = INCLUDE.findall(page.read_text())
            self.assertEqual(included.count("/partials/header.html"), 1, page.name)
            self.assertEqual(included.count("/partials/footer.html"), 1, page.name)


# --- the pages ------------------------------------------------------


class WebsitePageTests(SimpleTestCase):
    def test_every_page_has_the_basics(self):
        for page in pages():
            document = Document(rendered(page))
            html = document.all("html")
            self.assertTrue(html and html[0].get("lang"), f"{page.name}: <html lang> missing")
            self.assertTrue(document.title.strip(), f"{page.name}: empty <title>")
            self.assertTrue(
                any(document.meta("name", "description")), f"{page.name}: no description"
            )
            self.assertTrue(document.meta("name", "viewport"), f"{page.name}: no viewport")
            self.assertEqual(len(document.all("h1")), 1, f"{page.name}: needs exactly one <h1>")
            stylesheets = [
                a.get("href") for a in document.all("link") if a.get("rel") == "stylesheet"
            ]
            self.assertEqual(stylesheets, ["/assets/css/site.css"], page.name)
            self.assertEqual(len(document.all("main")), 1, page.name)

    def test_every_image_has_alt_text(self):
        for page in pages():
            for attrs in Document(rendered(page)).all("img"):
                # alt="" is right for a decorative image; a missing alt never is.
                self.assertIn("alt", attrs, f"{page.name}: {attrs.get('src')}")

    def test_nothing_inline_that_the_csp_would_block(self):
        # The website's policy is default-src 'self' (Caddyfile), so an
        # inline script, style or handler would be silently blocked.
        for page in pages():
            document = Document(rendered(page))
            self.assertEqual(document.all("style"), [], f"{page.name}: <style> element")
            for attrs in document.all("script"):
                if attrs.get("type") != "application/ld+json":
                    self.assertTrue(attrs.get("src"), f"{page.name}: inline <script>")
            for tag, attrs in document.elements:
                self.assertNotIn("style", attrs, f"{page.name}: style attribute on <{tag}>")
                handlers = [name for name in attrs if name.startswith("on")]
                self.assertEqual(handlers, [], f"{page.name}: <{tag}> {handlers}")

    def test_internal_links_resolve(self):
        for page in pages():
            document = Document(rendered(page))
            for url in document.urls():
                with self.subTest(page=page.name, url=url):
                    if url.startswith(SITE_ORIGIN):
                        url = url[len(SITE_ORIGIN) :] or "/"
                    elif url.startswith(EXTERNAL):
                        continue
                    parts = urlsplit(url)
                    if not parts.path:
                        self.assertIn(parts.fragment, document.ids(), "no such id on this page")
                        continue
                    # Root-relative only: the partials are also rendered at
                    # /book/ (unit 5), where a relative link would point
                    # somewhere else.
                    self.assertTrue(parts.path.startswith("/"), "use a root-relative URL")
                    target = served_file(parts.path)
                    self.assertIsNotNone(target, "nothing is served at this path")
                    if parts.fragment:
                        self.assertIn(parts.fragment, Document(rendered(target)).ids())

    def test_the_link_check_catches_a_broken_link(self):
        self.assertIsNone(served_file("/no-such-page"))
        self.assertIsNone(served_file("/partials/header.html"))
        self.assertIsNone(served_file("/../Caddyfile"))
        self.assertEqual(served_file("/"), WEBSITE / "index.html")
        self.assertEqual(served_file("/services"), WEBSITE / "services.html")

    def test_canonical_urls_name_their_own_page(self):
        for page in indexable_pages():
            document = Document(page.read_text())
            canonical = [a.get("href") for a in document.all("link") if a.get("rel") == "canonical"]
            expected = SITE_ORIGIN + clean_path(page)
            self.assertEqual(canonical, [expected], page.name)
            self.assertEqual(document.meta("property", "og:url"), [expected], page.name)

    def test_the_404_page_is_not_indexed(self):
        document = Document((WEBSITE / "404.html").read_text())
        self.assertEqual(document.meta("name", "robots"), ["noindex"])
        self.assertFalse([a for a in document.all("link") if a.get("rel") == "canonical"])

    def test_the_sitemap_lists_every_page_and_nothing_else(self):
        tree = ElementTree.parse(WEBSITE / "sitemap.xml")
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        listed = {loc.text.strip() for loc in tree.getroot().findall("s:url/s:loc", namespace)}
        self.assertEqual(listed, {SITE_ORIGIN + clean_path(page) for page in indexable_pages()})

    def test_robots_names_the_sitemap(self):
        self.assertIn(f"Sitemap: {SITE_ORIGIN}/sitemap.xml", (WEBSITE / "robots.txt").read_text())


# --- what Caddy does for the website hostnames (ADR 0016) -----------


def site_routes(config, host):
    """The top-level routes, and error routes, that serve `host`."""
    found = []
    for server in config["apps"]["http"]["servers"].values():
        for route in server.get("routes", []) + server.get("errors", {}).get("routes", []):
            if any(host in match.get("host", []) for match in route.get("match", [])):
                found.append(route)
    return found


def handlers(route):
    """Every handler anywhere under a route."""
    found = []
    for handle in route.get("handle", []):
        found.append(handle)
        for nested in handle.get("routes", []):
            found.extend(handlers(nested))
    return found


def proxied_paths(route, paths=()):
    """For each reverse_proxy under a route, the paths that reach it.

    An empty tuple means no path matcher stands in front of it: every
    path reaches it.
    """
    here = tuple(path for match in route.get("match", []) for path in match.get("path", []))
    here = here or paths
    found = []
    for handle in route.get("handle", []):
        if handle.get("handler") == "reverse_proxy":
            found.append(here)
        for nested in handle.get("routes", []):
            found.extend(proxied_paths(nested, here))
    return found


def routes_for_path(route, path):
    found = []
    if any(path in match.get("path", []) for match in route.get("match", [])):
        found.append(route)
    for handle in route.get("handle", []):
        for nested in handle.get("routes", []):
            found.extend(routes_for_path(nested, path))
    return found


def file_server_blocks(route):
    """The handlers of each handle block that serves files."""
    blocks = []
    for handle in route.get("handle", []):
        if handle.get("handler") == "subroute":
            own = [h for nested in handle.get("routes", []) for h in nested.get("handle", [])]
            if any(h.get("handler") == "file_server" for h in own):
                blocks.append(own)
            for nested in handle.get("routes", []):
                blocks.extend(file_server_blocks(nested))
    return blocks


@skipIf(not CADDY, "needs the caddy binary; CI installs it")
class WebsiteProxyConfigTests(SimpleTestCase):
    """Read from `caddy adapt`, the configuration Caddy actually runs —
    the lesson of logs/claude/phase-18-unit1-private-media.md. Each
    negative assertion is paired with a positive one using the same
    walker, so a walker that finds nothing fails instead of passing."""

    # (config, CRM hostname, a website hostname)
    SITES = (
        ("Caddyfile", CADDY_ENV["CRM_HOST"], CADDY_ENV["WEBSITE_HOST"]),
        ("Caddyfile", CADDY_ENV["CRM_HOST"], CADDY_ENV["WEBSITE_WWW_HOST"]),
        ("Caddyfile.dev", "localhost", "www.localhost"),
    )

    def setUp(self):
        self.configs = {name: adapt(ROOT / name) for name in {s[0] for s in self.SITES}}

    def test_the_website_hostnames_reach_no_part_of_the_crm(self):
        for name, crm, website in self.SITES:
            with self.subTest(config=name, host=website):
                routes = site_routes(self.configs[name], website)
                self.assertTrue(routes, "no site block serves this hostname")
                for paths in [p for route in routes for p in proxied_paths(route)]:
                    self.assertTrue(paths, "every path on the website reaches Django")
                    self.assertLessEqual(set(paths), ALLOWED_PROXY_PATHS, paths)

    def test_the_crm_hostname_still_reaches_django(self):
        for name, crm, _ in self.SITES:
            with self.subTest(config=name):
                routes = site_routes(self.configs[name], crm)
                self.assertTrue(routes, "no site block serves the CRM hostname")
                proxied = [p for route in routes for p in proxied_paths(route)]
                self.assertIn((), proxied, "the CRM's catch-all no longer proxies to Django")

    def test_the_website_serves_only_its_own_folder(self):
        for name, _, website in self.SITES:
            with self.subTest(config=name, host=website):
                found = [h for r in site_routes(self.configs[name], website) for h in handlers(r)]
                roots = {h["root"] for h in found if "root" in h}
                self.assertEqual(roots, {"/srv/website"})
                self.assertIn("file_server", {h.get("handler") for h in found})

    def test_partials_are_not_served(self):
        for name, _, website in self.SITES:
            with self.subTest(config=name, host=website):
                matched = [
                    r
                    for route in site_routes(self.configs[name], website)
                    for r in routes_for_path(route, "/partials/*")
                ]
                self.assertTrue(matched, "nothing refuses /partials/*")
                for route in matched:
                    kinds = {h.get("handler") for h in handlers(route)}
                    self.assertNotIn("file_server", kinds)
                    self.assertTrue(kinds & {"error", "static_response"}, kinds)

    def test_templates_run_on_html_only(self):
        for name, _, website in self.SITES:
            with self.subTest(config=name, host=website):
                templates = [
                    h
                    for r in site_routes(self.configs[name], website)
                    for h in handlers(r)
                    if h.get("handler") == "templates"
                ]
                self.assertTrue(templates, "no templates handler — the partials are not included")
                for handler in templates:
                    self.assertEqual(handler.get("mime_types"), ["text/html"])

    def test_every_website_file_carries_the_security_headers(self):
        for name, _, website in self.SITES:
            with self.subTest(config=name, host=website):
                blocks = [
                    block
                    for route in site_routes(self.configs[name], website)
                    for block in file_server_blocks(route)
                ]
                self.assertTrue(blocks, "no file-serving block found")
                for block in blocks:
                    headers = set()
                    for handler in block:
                        if handler.get("handler") == "headers":
                            headers |= set(handler.get("response", {}).get("set", {}))
                    for header in ("Content-Security-Policy", "X-Content-Type-Options"):
                        self.assertIn(header, headers)


# --- .env.example, the way the backup script reads .env --------------


class EnvExampleTests(SimpleTestCase):
    def test_env_example_sources_as_shell(self):
        """scripts/backup.sh runs `. .env` under `set -e`.

        A space in an unquoted value (`WEBSITE_HOSTS=a b`, as first
        planned) runs the second word as a command and stops the backup
        with exit 127. Reproduced while writing ADR 0016; this keeps the
        example from teaching that line.
        """
        result = subprocess.run(
            [
                "sh",
                "-c",
                'set -e; set -a; . "$1"; printf "%s|%s" "$CRM_HOST" "$WEBSITE_HOST"',
                "sh",
                str(ROOT / ".env.example"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        crm, website = result.stdout.split("|")
        self.assertTrue(crm and website, "CRM_HOST and WEBSITE_HOST must both be in .env.example")
