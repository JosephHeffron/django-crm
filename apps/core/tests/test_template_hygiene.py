"""The content policy, enforced rather than asserted in a comment.

`config/settings/production.py` says this app has "zero inline
scripts/styles of its own anywhere in templates/ (grep-confirmed)".
That claim was false: one inline style had been sitting in
crm/task_detail.html, behind an `{% if %}`, so the browser sweep that
checks for policy violations never rendered it. A grep in a comment
ages; a test does not.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)
# All three patterns are deliberately loose about case, whitespace and
# quoting. The first version matched only lowercase `style="` with no
# space and a double quote, which would have missed `STYLE =` and
# `style='` — a guard that only catches the spelling you happened to
# write is the kind of test this project has already been bitten by.
INLINE_STYLE_ATTR = re.compile(r"""\sstyle\s*=\s*["'`]?""", re.IGNORECASE)
STYLE_ELEMENT = re.compile(r"<style[\s>]", re.IGNORECASE)
# Unquoted values count too: onclick=go() is just as inline.
EVENT_HANDLER = re.compile(r"""\son[a-z]+\s*=\s*["']?\S""", re.IGNORECASE)
# A <script> with a body. A <script src=...></script> is external and fine.
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\ssrc\s*=)[^>]*>\s*\S", re.IGNORECASE)


def templates():
    seen = set()
    for pattern in ("templates/**/*.html", "apps/*/templates/**/*.html"):
        for path in ROOT.glob(pattern):
            if path not in seen:
                seen.add(path)
                yield path


class TemplateHygieneTests(SimpleTestCase):
    def test_there_are_templates_to_check(self):
        # A glob that matched nothing would make every test below pass.
        self.assertGreater(len(list(templates())), 50)

    def test_no_template_carries_an_inline_style(self):
        offenders = [
            str(path.relative_to(ROOT))
            for path in templates()
            if INLINE_STYLE_ATTR.search(path.read_text())
        ]
        self.assertEqual(offenders, [], "style-src has no 'unsafe-inline': these are blocked")

    def test_no_template_carries_a_style_element(self):
        # An inline <style> block is blocked by the same directive, and
        # the attribute pattern above would not see it.
        offenders = [
            str(path.relative_to(ROOT))
            for path in templates()
            if STYLE_ELEMENT.search(path.read_text())
        ]
        self.assertEqual(offenders, [], "an inline <style> block is blocked too")

    def test_no_template_carries_an_inline_script(self):
        offenders = [
            str(path.relative_to(ROOT))
            for path in templates()
            if INLINE_SCRIPT.search(path.read_text())
        ]
        self.assertEqual(offenders, [], "script-src has no 'unsafe-inline': these are blocked")

    def test_the_patterns_catch_what_they_are_meant_to(self):
        """The guards are only worth what they match.

        Checked here rather than trusted, because the first version of
        each pattern was narrower than it looked.
        """
        for markup in (
            ' style="x"',
            " style='x'",
            ' STYLE = "x"',
            "\tstyle=x",
        ):
            self.assertTrue(INLINE_STYLE_ATTR.search(markup), markup)
        for markup in (' onclick="go()"', " onClick=go()", ' ONERROR = "x"'):
            self.assertTrue(EVENT_HANDLER.search(markup), markup)
        for markup in ("<style>", "<STYLE type='text/css'>", "<style\n>"):
            self.assertTrue(STYLE_ELEMENT.search(markup), markup)
        self.assertTrue(INLINE_SCRIPT.search("<script>alert(1)</script>"))
        # And not over-match what is perfectly allowed.
        self.assertIsNone(INLINE_SCRIPT.search('<script src="/x.js" defer></script>'))
        self.assertIsNone(INLINE_STYLE_ATTR.search('<link rel="stylesheet" href="x.css">'))
        self.assertIsNone(EVENT_HANDLER.search('<a href="x">one</a>'))

    def test_no_template_carries_an_event_handler_attribute(self):
        offenders = [
            str(path.relative_to(ROOT))
            for path in templates()
            if EVENT_HANDLER.search(path.read_text())
        ]
        self.assertEqual(offenders, [], "onclick and friends are inline script")
