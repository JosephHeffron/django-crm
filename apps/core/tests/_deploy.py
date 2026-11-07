"""Running the real `scripts/deploy.sh` in throwaway git repositories.

Shared by the website-only deploy tests (test_website_fast_paths.py)
and the full-deploy tests (test_deploy_script.py). Each test gets an
origin, a "server" checkout that the script deploys in, and a
"developer" clone that pushes new commits. `curl`, `podman` and
`podman-compose` are stubs on PATH that record how they were called,
in `logs/curl` and `logs/containers`.

The stubs answer the way the real stack would when it is healthy, and
environment switches make them fail the way it fails:

  STUB_CURL_FAIL=1   every request fails, like Caddy being down
  STUB_CRM_DOWN=1    only the CRM's /health/ fails
  STUB_HEALTH=x      `podman inspect` reports x instead of healthy

A page request returns the checkout's own website/index.html, so what
a commit puts there is what the deploy's website check sees.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

ROOT = Path(settings.BASE_DIR)
DEPLOY = ROOT / "scripts" / "deploy.sh"
SCOPE = ROOT / "scripts" / "change-scope.sh"
GIT = shutil.which("git")

CURL_STUB = """#!/bin/sh
echo "$@" >>"$STUB_LOG/curl"
[ -z "${STUB_CURL_FAIL:-}" ] || { echo "curl: (7) Failed to connect" >&2; exit 7; }
case "$*" in
*/health/*)
	[ -z "${STUB_CRM_DOWN:-}" ] || { echo "curl: (22) 503" >&2; exit 22; }
	echo '{"status": "ok", "database": "ok"}'
	;;
*) cat "$STUB_SITE/website/index.html" ;;
esac
"""

PODMAN_STUB = """#!/bin/sh
echo "podman $*" >>"$STUB_LOG/containers"
[ "$1" = inspect ] && echo "${STUB_HEALTH:-healthy}"
exit 0
"""

COMPOSE_STUB = """#!/bin/sh
echo "podman-compose $*" >>"$STUB_LOG/containers"
exit 0
"""

GOOD_PAGE = '<header class="site-header">Heffron</header><main>home</main>\n'


def skips_certificate_checks(curl_log):
    """Whether any recorded curl call turned off certificate checks.

    Reads combined short flags too: `-kfsS` is as insecure as `-k`.
    """
    for call in curl_log.splitlines():
        for arg in call.split():
            if arg == "--insecure":
                return True
            if arg.startswith("-") and not arg.startswith("--") and "k" in arg[1:]:
                return True
    return False


class DeployHarness:
    """setUp and helpers for a SimpleTestCase that runs deploy.sh."""

    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.origin = self.tmp / "origin.git"
        self.server = self.tmp / "server"
        self.dev = self.tmp / "dev"
        self.logs = self.tmp / "logs"
        self.bin = self.tmp / "bin"
        self.logs.mkdir()
        self.bin.mkdir()
        for name, body in (
            ("curl", CURL_STUB),
            ("podman", PODMAN_STUB),
            ("podman-compose", COMPOSE_STUB),
        ):
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)

        self.env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "STUB_LOG": str(self.logs),
            "STUB_SITE": str(self.server),
            # A failing deploy retries; these keep it to seconds.
            "HEALTH_CHECK_INTERVAL": "0",
            "CADDY_CHECK_RETRIES": "1",
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.test",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.test",
        }
        self.git(self.tmp, "init", "--bare", "--quiet", str(self.origin))
        self.git(self.origin, "symbolic-ref", "HEAD", "refs/heads/main")
        self.git(self.tmp, "clone", "--quiet", str(self.origin), str(self.dev))
        self.git(self.dev, "checkout", "--quiet", "-B", "main")
        self.write(
            self.dev,
            {
                "scripts/deploy.sh": DEPLOY.read_text(),
                "scripts/change-scope.sh": SCOPE.read_text(),
                "website/index.html": GOOD_PAGE,
                "website/about.html": "<p>about</p>\n",
                "website/partials/header.html": '<header class="site-header"></header>\n',
                "apps/app.py": "VALUE = 1\n",
                ".gitignore": ".env\n.deploy-last-good-ref\n",
            },
        )
        self.deployed = self.push("initial")
        self.git(self.tmp, "clone", "--quiet", str(self.origin), str(self.server))
        (self.server / ".env").write_text("CRM_HOST=crm.example.test\nWEBSITE_HOST=example.test\n")

    def git(self, cwd, *args):
        return subprocess.run(
            ["git", *args], cwd=cwd, env=self.env, capture_output=True, text=True, check=True
        ).stdout.strip()

    def write(self, repo, files):
        for name, body in files.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)

    def push(self, message, files=None):
        """Commit `files` in the developer clone, push, return the SHA."""
        self.write(self.dev, files or {})
        self.git(self.dev, "add", "-A")
        self.git(self.dev, "commit", "--quiet", "-m", message)
        self.git(self.dev, "push", "--quiet", "origin", "main")
        return self.git(self.dev, "rev-parse", "HEAD")

    def deploy(self, *args, **env):
        return subprocess.run(
            ["sh", str(self.server / "scripts" / "deploy.sh"), *args],
            cwd=self.server,
            env={**self.env, **env},
            capture_output=True,
            text=True,
        )

    def head(self):
        return self.git(self.server, "rev-parse", "HEAD")

    def log(self, name):
        path = self.logs / name
        return path.read_text() if path.exists() else ""

    def state(self):
        path = self.server / ".deploy-last-good-ref"
        return path.read_text().strip() if path.exists() else None
