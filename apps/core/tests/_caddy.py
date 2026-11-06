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
