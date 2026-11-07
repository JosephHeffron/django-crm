"""A backup that fails, or never runs, must be noticed (audit F-BAK-3, F-BAK-4).

`scripts/backup.sh` requests `BACKUP_PING_URL` once it has finished,
off-host push included, and a monitoring service raises the alarm when
a day passes without that request. These tests run the real script end
to end in a throwaway git checkout, with `podman`, `restic` and `curl`
stubbed on PATH. The stubs record every call in one shared log, in
order, so the tests can assert *when* the monitor is told, not only
whether.

What matters, in order of how badly it would hurt to get wrong:

- a failed backup or a failed push never pings, because a ping is the
  "all is well" signal and a false one silences the only alarm;
- a backup that never left the host never pings, because that is how a
  misconfigured deployment looks (F-BAK-4);
- the URL never appears in the output, because it is a credential;
- an unreachable monitor does not turn a good backup into a failed one.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)
BACKUP = ROOT / "scripts" / "backup.sh"
PING = "https://hc-ping.com/00000000-test-ping-secret"

PODMAN_STUB = r"""#!/bin/sh
echo "podman $*" >>"$STUB_LOG"
case "$1" in
exec)
	case "$*" in
	*pg_dump*) printf 'PGDMP fake archive' ;;
	*"pg_restore --list"*) [ -z "${STUB_BAD_DUMP:-}" ] || exit 1 ;;
	esac
	;;
volume)
	if [ "$2" = export ]; then
		while [ $# -gt 0 ]; do
			[ "$1" = "-o" ] && : >"$2"
			shift
		done
	fi
	;;
esac
exit 0
"""

RESTIC_STUB = r"""#!/bin/sh
echo "restic $1" >>"$STUB_LOG"
[ "$1" = backup ] && [ -n "${STUB_RESTIC_FAIL:-}" ] && exit 1
exit 0
"""

CURL_STUB = r"""#!/bin/sh
echo "curl $*" >>"$STUB_LOG"
[ -z "${STUB_CURL_FAIL:-}" ] || { echo "curl: (6) Could not resolve host" >&2; exit 6; }
exit 0
"""


class BackupMonitoringTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "repo"
        self.bin = self.tmp / "bin"
        self.log = self.tmp / "calls.log"
        (self.repo / "scripts").mkdir(parents=True)
        self.bin.mkdir()
        (self.repo / "scripts" / "backup.sh").write_text(BACKUP.read_text())
        for name, body in (("podman", PODMAN_STUB), ("restic", RESTIC_STUB), ("curl", CURL_STUB)):
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "STUB_LOG": str(self.log),
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.test",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.test",
        }
        # The manifest records `git rev-parse HEAD`.
        for args in (["init", "--quiet"], ["add", "-A"], ["commit", "--quiet", "-m", "init"]):
            subprocess.run(["git", *args], cwd=self.repo, env=self.env, check=True)

    def env_file(self, *, restic=True, ping=True):
        lines = ["POSTGRES_DB=crm", "POSTGRES_USER=crm"]
        if restic:
            lines += [
                "RESTIC_REPOSITORY=b2:bucket:django-crm",
                "RESTIC_PASSWORD=not-a-real-password",
            ]
        if ping:
            lines.append(f"BACKUP_PING_URL={PING}")
        (self.repo / ".env").write_text("\n".join(lines) + "\n")

    def backup(self, **env):
        return subprocess.run(
            ["sh", str(self.repo / "scripts" / "backup.sh")],
            cwd=self.repo,
            env={**self.env, **env},
            capture_output=True,
            text=True,
        )

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def pings(self):
        return [call for call in self.calls() if call.startswith("curl ")]

    # --- the monitor hears about a good backup, and only then -------

    def test_a_good_backup_pings_once_after_the_push(self):
        self.env_file()
        result = self.backup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.pings()), 1)
        self.assertIn(PING, self.pings()[0])
        # Last of all: after the snapshot and the retention pass.
        self.assertTrue(self.calls()[-1].startswith("curl "), self.calls()[-3:])
        self.assertIn("restic backup", self.calls())
        self.assertIn("restic forget", self.calls())

    def test_the_ping_has_a_timeout_and_retries(self):
        self.env_file()
        self.backup()
        call = self.pings()[0]
        self.assertIn("--max-time", call)
        self.assertIn("--retry", call)
        short_flags = "".join(
            arg[1:] for arg in call.split() if arg.startswith("-") and not arg.startswith("--")
        )
        self.assertIn("f", short_flags, "a 4xx/5xx from the monitor must count as failed")

    def test_a_failed_push_never_pings(self):
        self.env_file()
        result = self.backup(STUB_RESTIC_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.pings(), [])

    def test_an_unreadable_dump_never_pings(self):
        self.env_file()
        result = self.backup(STUB_BAD_DUMP="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.pings(), [])
        self.assertNotIn("restic backup", self.calls())

    def test_a_local_only_backup_never_pings_and_says_why(self):
        self.env_file(restic=False)
        result = self.backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.pings(), [])
        self.assertIn("RESTIC_REPOSITORY is not", result.stderr)

    def test_no_ping_url_means_no_request(self):
        self.env_file(ping=False)
        result = self.backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.pings(), [])

    # --- the ping itself ---------------------------------------------

    def test_an_unreachable_monitor_does_not_fail_a_good_backup(self):
        self.env_file()
        result = self.backup(STUB_CURL_FAIL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("could not reach the monitoring service", result.stderr)

    def test_the_url_is_never_printed(self):
        for kwargs, env in (
            ({}, {}),
            ({}, {"STUB_CURL_FAIL": "1"}),
            ({"restic": False}, {}),
        ):
            with self.subTest(**kwargs, **env):
                self.env_file(**kwargs)
                result = self.backup(**env)
                self.assertNotIn("hc-ping.com", result.stdout + result.stderr)
