"""A backup is only a backup if it can be read back.

QA audit finding QA-001. `backup.sh` wrote `db.dump` and checked
nothing about it; `restore.sh` required only that the file *exist*
(`[ -f ]`) and then destroyed the live `postgres_data` volume before
`pg_restore` ever opened it. A dump that was present but unusable
therefore cost the current database and gave nothing back.

Measured before fixing: `[ -f ]` accepts a 0-byte file, a 3-byte stub,
a truncated archive and a plain text file. A `PGDMP` magic-byte check
catches three of those four and **accepts the truncated one**, which is
the realistic failure — a partial write, a full disk, an interrupted
stream. Reading the archive's table of contents catches all four, which
is why both scripts now do that.

Two kinds of test here, and the distinction is the point:

- `ScriptOrderTests` reads the scripts. Weak on its own, but it is the
  only thing that can assert the check runs *before* the destructive
  step, and that is the whole property. It would catch the check being
  deleted or moved.
- `ArchiveValidationTests` runs the real `pg_restore` against real
  corrupt archives, so the mechanism the scripts rely on is verified
  rather than assumed. It skips where no `pg_restore` is installed, and
  says so, because a test that pretends to pass is worse than one that
  admits it did not run.

What neither covers: a full restore against a live stack. That needs
the production compose stack and real volumes, so it stays a manual
step in `docs/TESTING_INSTRUCTIONS.md`.
"""

import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

SCRIPTS = Path(settings.BASE_DIR) / "scripts"
PG_RESTORE = shutil.which("pg_restore")

# A valid PostgreSQL custom-format archive starts with these five
# bytes, confirmed against a real `pg_dump -Fc`.
CUSTOM_FORMAT_MAGIC = b"PGDMP"


def commands_only(script):
    """The script with comment lines removed.

    Written after the first version of these tests failed on the fix it
    was meant to guard: the explanatory comment above the verification
    in `restore.sh` mentions `podman volume rm`, so searching the raw
    text found the comment and concluded the check ran too late. An
    ordering assertion has to look at commands, not at prose about
    commands.
    """
    return "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))


class ScriptOrderTests(SimpleTestCase):
    def setUp(self):
        self.backup = commands_only((SCRIPTS / "backup.sh").read_text())
        self.restore = commands_only((SCRIPTS / "restore.sh").read_text())

    def test_backup_verifies_the_dump_it_just_wrote(self):
        self.assertIn("pg_restore --list", self.backup)

    def test_backup_verifies_after_writing_the_dump(self):
        """Checking before the dump exists would always fail."""
        wrote = self.backup.index('>"$DEST/db.dump"')
        verified = self.backup.index("pg_restore --list")
        self.assertLess(wrote, verified)

    def test_restore_verifies_the_dump_before_destroying_anything(self):
        """The finding, as an assertion.

        `podman volume rm` is the point of no return: the live database
        is gone after it. The verification has to sit above it, and a
        later refactor that reorders these is the regression this
        guards.
        """
        verified = self.restore.index("pg_restore --list")
        destroyed = self.restore.index("podman volume rm")
        self.assertLess(
            verified,
            destroyed,
            "restore.sh must read db.dump's table of contents before it removes "
            "the live postgres_data volume",
        )

    def test_restore_still_refuses_a_backup_with_files_missing(self):
        """The older, weaker check is kept, not replaced: a missing file
        should be named as missing rather than reported as unreadable."""
        self.assertIn('[ -f "$SRC/$f" ]', self.restore)

    def test_a_failed_verification_stops_the_restore(self):
        """A warning that proceeds anyway would not protect anything."""
        after = self.restore[self.restore.index("pg_restore --list") :]
        self.assertIn("exit 1", after[:800])

    def test_both_scripts_are_still_valid_posix_shell(self):
        for name in ("backup.sh", "restore.sh"):
            result = subprocess.run(
                ["sh", "-n", str(SCRIPTS / name)], capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")

    def test_the_db_image_is_discoverable_from_the_compose_file(self):
        """restore.sh verifies in a throwaway container from the db
        service's own image, so that lookup has to keep working."""
        for compose in ("compose.prod.yml", "compose.dev.yml"):
            text = (Path(settings.BASE_DIR) / compose).read_text()
            self.assertIn("postgres:", text, compose)


class ArchiveValidationTests(SimpleTestCase):
    """The mechanism both scripts depend on, against real archives."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = Path(settings.BASE_DIR) / ".qa-tmp-archives"
        cls.tmp.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        super().tearDownClass()

    def reads_cleanly(self, path):
        result = subprocess.run([PG_RESTORE, "--list", str(path)], capture_output=True, text=True)
        return result.returncode == 0

    def test_the_weak_check_really_does_accept_rubbish(self):
        """Why the fix was needed, asserted rather than asserted-at.

        This is the behaviour of the check that *used* to be the only
        one, so it documents the gap rather than the fix.
        """
        for name, content in (
            ("empty.dump", b""),
            ("stub.dump", b"PGD"),
            ("junk.dump", b"this is not a dump at all\n"),
        ):
            path = self.tmp / name
            path.write_bytes(content)
            self.assertTrue(path.is_file(), f"[ -f ] would accept {name}")

    def test_a_truncated_archive_keeps_the_magic_bytes(self):
        """The reason a magic-byte check is not enough.

        A truncated dump still begins with `PGDMP`, so a header check
        passes it — and truncation is the failure most likely to
        actually happen.
        """
        truncated = self.tmp / "trunc.dump"
        truncated.write_bytes(CUSTOM_FORMAT_MAGIC + b"\x01\x0f\x00" + b"\x00" * 2000)
        self.assertTrue(truncated.read_bytes().startswith(CUSTOM_FORMAT_MAGIC))

    def test_pg_restore_rejects_every_damaged_archive(self):
        if PG_RESTORE is None:
            self.skipTest("no pg_restore on this machine; see this module's docstring")
        for name, content in (
            ("empty.dump", b""),
            ("stub.dump", b"PGD"),
            ("junk.dump", b"this is not a dump at all\n"),
            ("trunc.dump", CUSTOM_FORMAT_MAGIC + b"\x01\x0f\x00" + b"\x00" * 2000),
        ):
            path = self.tmp / name
            path.write_bytes(content)
            self.assertFalse(self.reads_cleanly(path), f"{name} was accepted")
