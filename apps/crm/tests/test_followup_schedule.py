"""The daily follow-up timer (Phase 19 unit 1).

`generate_followups` has existed since Phase 17 and nothing ran it. The
roadmap asks for "daily follow-up generation via a systemd timer (same
pattern as the backup timer)", so this covers the three pieces that
pattern needs: a script the unit can call, a service unit that calls
it, and a timer that schedules the service.

What these can and cannot check is worth being clear about. They assert
the units are **valid systemd** — parsed by `systemd-analyze verify`,
not pattern-matched — and that the script refuses loudly when it cannot
reach the stack, which is testable because `podman container exists`
answers for a name that was never there. What they cannot do is run the
timer: that needs the production stack and a clock. The manual check is
in `docs/ADMIN_GUIDE.md`.

The failure that matters here is not a skipped day. Generation is
idempotent and due-ness is computed from "has the interval elapsed",
so a customer due yesterday is still due today and a missed run raises
the follow-up late rather than never. The failure that matters is the
timer being *broken* — a renamed container, a stack that never came
up — because then follow-ups stop silently and the only symptom is an
absence. Hence the insistence on a non-zero exit.
"""

import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)
SCRIPT = ROOT / "scripts" / "followups.sh"
UNITS = ROOT / "systemd"
SYSTEMD_ANALYZE = shutil.which("systemd-analyze")


class TheScriptTests(SimpleTestCase):
    def test_it_exists_and_is_executable(self):
        """systemd reports `Command ... is not executable` and refuses
        to start the unit otherwise, which is a confusing way to find
        out about a lost permission bit."""
        self.assertTrue(SCRIPT.exists())
        self.assertTrue(os.access(SCRIPT, os.X_OK), f"{SCRIPT} is not executable")

    def test_it_is_valid_posix_shell(self):
        result = subprocess.run(["sh", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_it_stops_on_error(self):
        self.assertIn("set -e", SCRIPT.read_text())

    def test_it_runs_the_command_inside_the_web_container(self):
        """Django lives in the container; the host has no application
        environment at all, so this cannot be a bare `manage.py`."""
        text = SCRIPT.read_text()
        self.assertIn("podman exec", text)
        self.assertIn("manage.py generate_followups", text)

    def test_it_forwards_its_arguments(self):
        """`--date` is how the command is exercised by hand against a
        past day; a script that swallowed it would look like it worked.
        """
        self.assertIn('generate_followups "$@"', SCRIPT.read_text())

    def test_it_refuses_loudly_when_the_stack_is_not_there(self):
        """The real failure mode: follow-ups stopping in silence.

        Run against a container name that cannot exist. This needs no
        stack — `podman container exists` simply answers no — so it is a
        genuine behavioural test rather than a reading of the script.
        """
        if shutil.which("podman") is None:
            self.skipTest("no podman on this machine")
        result = subprocess.run(
            [str(SCRIPT)],
            capture_output=True,
            text=True,
            env={**os.environ, "SERVICE_PREFIX": "definitely-not-a-real-stack"},
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 1, "a missing stack must be a failure, not a no-op")
        self.assertIn("definitely-not-a-real-stack_web_1", result.stderr)
        self.assertIn("SERVICE_PREFIX", result.stderr)


class TheUnitsTests(SimpleTestCase):
    """Valid systemd, checked by systemd rather than by a regex."""

    def verify(self, name):
        """`systemd-analyze verify`, with `%h` pointed at this checkout.

        The units are written for the deployment layout
        (`%h/django-crm`), which does not exist on a development
        machine, so verifying them as-written reports the ExecStart
        path as missing — exactly as it does for the long-standing
        `crm-backup.service`. Substituting the real checkout isolates
        everything else, which is the part worth asserting.
        """
        source = (UNITS / name).read_text()
        target = Path(self.tmp) / name
        target.write_text(source.replace("%h/django-crm", str(ROOT)))
        result = subprocess.run(
            [SYSTEMD_ANALYZE, "verify", "--user", str(target)],
            capture_output=True,
            text=True,
        )
        return (result.stdout + result.stderr).strip()

    def setUp(self):
        if SYSTEMD_ANALYZE is None:
            self.skipTest("no systemd-analyze on this machine")
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_the_service_unit_is_valid(self):
        self.assertEqual(self.verify("crm-followups.service"), "")

    def test_the_timer_unit_is_valid(self):
        self.assertEqual(self.verify("crm-followups.timer"), "")

    def test_the_backup_units_are_still_valid(self):
        """The pattern being copied. If these ever stop verifying, the
        comparison the new units rest on is gone.
        """
        self.assertEqual(self.verify("crm-backup.service"), "")
        self.assertEqual(self.verify("crm-backup.timer"), "")


class WhatTheUnitsSayTests(SimpleTestCase):
    """Properties a valid unit can still get wrong."""

    def setUp(self):
        self.service = (UNITS / "crm-followups.service").read_text()
        self.timer = (UNITS / "crm-followups.timer").read_text()

    def test_the_service_runs_the_followups_script(self):
        self.assertIn("scripts/followups.sh", self.service)

    def test_the_service_is_a_oneshot(self):
        """A `simple` service would be considered failed the moment the
        script exited, however well it went."""
        self.assertIn("Type=oneshot", self.service)

    def test_the_service_waits_for_the_stack(self):
        """`podman exec` needs the container to exist first."""
        self.assertIn("After=crm.service", self.service)

    def test_the_timer_runs_daily(self):
        self.assertIn("OnCalendar=", self.timer)
        self.assertIn("07:00", self.timer)

    def test_the_timer_catches_up_after_downtime(self):
        """Without `Persistent`, a Pi that was off at 07:00 skips the
        day entirely rather than running at the next boot."""
        self.assertIn("Persistent=true", self.timer)

    def test_the_timer_installs_itself_into_timers_target(self):
        """`systemctl --user enable` has nothing to do otherwise, and
        reports success anyway."""
        self.assertIn("WantedBy=timers.target", self.timer)

    def test_the_service_is_not_itself_enabled(self):
        """The timer is what gets enabled. A service unit carrying its
        own `[Install]` invites enabling it directly, which would run
        the generation once at boot and never again.
        """
        self.assertNotIn("[Install]", self.service)
