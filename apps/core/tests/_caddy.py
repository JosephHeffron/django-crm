"""Running Caddy's own adapter from the test suite.

Shared by apps/jobs/tests/test_private_media.py and
apps/core/tests/test_website.py, so every test that reads the
production Caddyfile gives it the same site addresses.
"""

import json
import os
import shutil
import subprocess

CADDY = shutil.which("caddy")

# Every variable the production Caddyfile reads
# (docs/decisions/0016-two-sites-behind-one-caddy.md). Any values adapt
# the same, but a variable left out makes `caddy validate` fail for a
# reason that has nothing to do with what the test guards — audit
# finding F-CAD-3 — so a new variable in the Caddyfile belongs here in
# the same change.
CADDY_ENV = {
    "CRM_HOST": "crm.example.test",
    "WEBSITE_HOST": "example.test",
    "WEBSITE_WWW_HOST": "www.example.test",
}


def caddy_env():
    return {**os.environ, **CADDY_ENV}


def adapt(path):
    """The JSON configuration Caddy will actually run for `path`."""
    raw = subprocess.run(
        ["caddy", "adapt", "--config", str(path)],
        capture_output=True,
        text=True,
        check=True,
        env=caddy_env(),
    ).stdout
    return json.loads(raw)


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


# The handlers that write a response and end the request. Everything
# else this config uses (encode, headers, vars, rewrite, templates)
# shapes a response or the request and passes it on.
ANSWERING = {"static_response", "error", "file_server", "reverse_proxy", "abort"}


def _path_matches(pattern, path):
    return path.startswith(pattern[:-1]) if pattern.endswith("*") else path == pattern


def _applies(route, host, path):
    """Whether a route's matchers admit this host and path.

    Only host and path matchers are modelled. A matcher set with any
    other kind (try_files' `file`, an `expression`) is treated as not
    matching, which is what those do for the requests the tests ask
    about; a test that needs one modelled must add it here.
    """
    matcher_sets = route.get("match")
    if not matcher_sets:
        return True
    for matcher in matcher_sets:
        if set(matcher) - {"host", "path"}:
            continue
        if "host" in matcher and host not in matcher["host"]:
            continue
        if "path" in matcher and not any(_path_matches(p, path) for p in matcher["path"]):
            continue
        return True
    return False


def first_answer(routes, host, path):
    """The handler that would answer this request, or None.

    Walks routes in order the way Caddy runs them: a route applies when
    it has no matchers or one matcher set fits; its handlers run in
    order; a subroute is entered, and falls through when nothing in it
    answers; a terminal route that answers nothing ends the search.
    Path rewrites (handle_path's prefix strip) are not applied, so
    nested path matchers under one would be misread; this config has
    none.
    """
    for route in routes:
        if not _applies(route, host, path):
            continue
        for handler in route.get("handle", []):
            kind = handler.get("handler")
            if kind == "subroute":
                found = first_answer(handler.get("routes", []), host, path)
                if found is not None:
                    return found
            elif kind in ANSWERING:
                return handler
        if route.get("terminal"):
            return None
    return None


def answer_for(config, host, path):
    """`first_answer` across every server in an adapted config."""
    for server in config["apps"]["http"]["servers"].values():
        found = first_answer(server.get("routes", []), host, path)
        if found is not None:
            return found
    return None
