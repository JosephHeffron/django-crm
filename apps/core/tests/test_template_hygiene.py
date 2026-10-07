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
EVENT_HANDLER = re.compile(r"\son[a-z]+\s*=\s*[\"']", re.IGNORECASE)
# A <script> with a body. A <script src=...></script> is external and fine.
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\ssrc=)[^>]*>\s*\S", re.IGNORECASE)


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
            str(path.relative_to(ROOT)) for path in templates() if 'style="' in path.read_text()
        ]
        self.assertEqual(offenders, [], "style-src has no 'unsafe-inline': these are blocked")

    def test_no_template_carries_an_inline_script(self):
        offenders = [
            str(path.relative_to(ROOT))
            for path in templates()
            if INLINE_SCRIPT.search(path.read_text())
        ]
        self.assertEqual(offenders, [], "script-src has no 'unsafe-inline': these are blocked")

    def test_no_template_carries_an_event_handler_attribute(self):
        offenders = [
            str(path.relative_to(ROOT))
            for path in templates()
            if EVENT_HANDLER.search(path.read_text())
        ]
        self.assertEqual(offenders, [], "onclick and friends are inline script")
