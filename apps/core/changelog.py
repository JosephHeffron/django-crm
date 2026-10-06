"""What's new, read from CHANGELOG.md (Phase 17.5 step 10).

One place to write a release note, not two. The file is the project's
own changelog in Keep a Changelog form, so this parses exactly that
shape and nothing cleverer: a `## [version] - date` line starts a
release, `### Added` and friends group what follows, and `- ` lines are
the entries.

Anything it can't parse is skipped rather than guessed at, so a
malformed heading costs one release, not the page.
"""

import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

RELEASE = re.compile(r"^##\s+\[?([^\]]+?)\]?(?:\s+-\s+(.+))?$")
GROUP = re.compile(r"^###\s+(.+)$")
ENTRY = re.compile(r"^[-*]\s+(.+)$")
MAX_RELEASES = 20


def path():
    return Path(settings.BASE_DIR) / "CHANGELOG.md"


@lru_cache(maxsize=1)
def _parse(text):
    releases = []
    current = None
    group = None
    for line in text.splitlines():
        heading = RELEASE.match(line.strip())
        if heading:
            current = {
                "version": heading.group(1).strip(),
                "date": (heading.group(2) or "").strip(),
                "groups": [],
            }
            releases.append(current)
            group = None
            continue
        if current is None:
            continue
        grouped = GROUP.match(line.strip())
        if grouped:
            group = {"name": grouped.group(1).strip(), "entries": []}
            current["groups"].append(group)
            continue
        entry = ENTRY.match(line.strip())
        if entry and group is not None:
            group["entries"].append(entry.group(1).strip())
            continue
        # A bullet that wraps belongs to the bullet above it. Without
        # this, a note written across two lines loses everything after
        # the first.
        if group is not None and group["entries"] and line.strip():
            group["entries"][-1] += " " + line.strip()
    return [release for release in releases if release["groups"]][:MAX_RELEASES]


def releases():
    """Newest first, as the file is written. Returns nothing at all if
    the file is missing — a page that can't find its notes should say
    so, not fall over."""
    try:
        text = path().read_text(encoding="utf-8")
    except OSError:
        return []
    return _parse(text)
