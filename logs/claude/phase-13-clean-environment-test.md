# PHASE 13: CLEAN-ENVIRONMENT END-TO-END TEST (UNIT 2)

Started: 2026-09-17
Ended: 2026-09-17

## Objective

Second and final unit of Phase 13, per the roadmap: a clean-
environment end-to-end test, proving the whole system works as
documented for a first-time deployer, tying together every
script/doc Phases 7-13 have produced.

## Files created / changed

- `docs/CLEAN_ENVIRONMENT_TEST.md` — new. Full walkthrough write-up
  and the one real bug found.
- `scripts/backup.sh` / `scripts/restore.sh` — added a `VOLUME_SUFFIX`
  environment variable (default empty) and an explicit `podman volume
  exists` check in `backup.sh` (see below).

## Commands

$ `git clone https://github.com/JosephHeffron/django-crm.git` — a
  real clone from the real public remote, into an isolated scratch
  location, not a local shortcut.

$ Attempted the README's native dev setup (fresh venv — succeeded;
  `sudo -u postgres createuser`/`createdb` with an isolated role
  name — failed: `sudo: a password is required`, no interactive TTY
  available in this environment). Presented to the user as a choice;
  the user chose to skip native dev setup and focus this unit on the
  production deployment path (rootless Podman, no sudo needed).

$ Configured `.env` from `.env.example`, following only that file's
  own comments — confirmed it still has no `DJANGO_SETTINGS_MODULE`
  line (Phase 11's fix holds for a genuinely fresh clone).

$ Installed `systemd/crm.service` exactly per its own header comment's
  install instructions, adapted only in `WorkingDirectory` (this
  clone's actual path) and the compose file referenced
  (`compose.dev.yml`, since no real public domain exists locally for
  real Let's Encrypt). `systemctl --user enable --now` brought up all
  three containers, all healthy.

$ **Real functional verification, not just HTTP status codes**:
  created a superuser, logged in with a real cookie-jar/CSRF round
  trip through Caddy, confirmed the dashboard rendered showing the
  logged-in user. Submitted the real "add Company" form the same way
  — first attempt got a `403` (the CSRF token extracted was the
  page's *logout*-form token, not the add-Company form's own; the
  page has two), corrected by extracting the right one — second
  attempt succeeded, and the new Company record was confirmed present
  in the real list view afterward.

$ `scripts/backup.sh` (with `SERVICE_PREFIX`/`COMPOSE_FILE` set to
  match this test's clone) — reported success.
Result: **silently wrong**. Investigated: `media_files.tar` was
3584 bytes and contained none of the real data. **Root cause**:
`compose.dev.yml`'s volumes all carry a `_dev` suffix
(`media_files_dev`, etc. — added in Phase 7 specifically so
`compose.dev.yml`'s stack never shares volumes with
`compose.prod.yml`'s), which `scripts/backup.sh`'s hardcoded volume
names don't account for — exactly the combination the script's own
header comment offered as a documented usage example
(`COMPOSE_FILE=compose.dev.yml`).

$ Investigated *why* this failed silently rather than loudly under
  `set -e`: `podman volume export <name>` for a name that doesn't
  appear in `podman volume ls` was confirmed, live, to still exit `0`
  and produce a small, valid-looking, empty tar on this project's
  Podman version — not the immediate, loud failure a missing resource
  would normally produce (confirmed by contrast against a definitely-
  nonexistent name in isolation, which *did* fail as expected — the
  discrepancy traced to Podman's own behavior for this specific
  command, not a scripting mistake).

$ Fixed two ways: a `VOLUME_SUFFIX` environment variable (default
  empty — `compose.prod.yml` behavior, and therefore real production
  use, completely unaffected) appended to every volume name in both
  `scripts/backup.sh` and `scripts/restore.sh`; and an explicit
  `podman volume exists` check in `backup.sh` before attempting each
  export, failing loudly with a clear error rather than trusting
  `podman volume export`'s own exit code.

$ Re-ran the **entire lifecycle a second time** with the fix applied:
  recreated the superuser/Company record, `scripts/backup.sh` with
  `VOLUME_SUFFIX=_dev` (confirmed `media_files.tar` now genuinely
  contained the marker file), simulated total disaster (tore down
  every container, removed every volume, confirmed nothing remained),
  `scripts/restore.sh` with the same flag.
Result: **PASS**. The real Company record (created through the actual
web form, not a raw SQL insert) and the media marker file were both
confirmed present after recovery; the app served real pages through
Caddy afterward.

$ Cleanup: `systemctl --user stop` (its own `ExecStop` tore the stack
  down correctly), disabled and removed the unit, removed all
  volumes, the built image, and the throwaway backup directories.
  Confirmed via `podman ps -a`/`systemctl --user list-units` that
  nothing was left behind.

$ `ruff check .` / `manage.py check`
Result: PASS (this unit is shell scripts + a doc, no Python
application code).

$ `python manage.py test` (full suite)
Result: PASS — 303 tests (unchanged).

## Tests

`python manage.py test` — 303 passed, 0 failures.
Two full live disaster-recovery lifecycles against a genuinely fresh
clone (before and after the fix) — the unit's real test.

## Decisions

- Used isolated, throwaway identifiers throughout (a distinct
  PostgreSQL role name attempted, a distinct systemd unit name, the
  clone's own directory-derived Podman project name) specifically so
  nothing in this test could collide with or affect this
  workstation's real, already-existing local development environment
  — same discipline established since Phase 8, applied here to a
  genuinely new clone rather than a copy of the working repo.
- Skipped native dev setup verification rather than work around the
  sudo/TTY limitation with something less faithful (e.g. `sudo -S`
  reading a password from a variable, which would mean handling a
  real or fake password in a way this project's LOGGING/secrets
  discipline would frown on for a throwaway test) — presented the
  blocker to the user plainly instead.
- `VOLUME_SUFFIX` defaults to empty specifically so this fix is
  invisible to real production use — the bug it fixes only ever
  manifested for the `compose.dev.yml` combination, and the fix
  shouldn't add any new consideration for the `compose.prod.yml` path
  that's already been tested throughout Phase 11.

## Errors

One real, substantive bug found and fixed during this unit's own live
verification — not from an automated review (repo is public again as
of Phase 13 unit 1, and Sourcery did review this PR, but hit its
free-tier budget limit before producing line-level findings; this
unit's own two full live lifecycle tests already served the
equivalent scrutiny, more thoroughly than a single review pass would
have):

1. `scripts/backup.sh`/`scripts/restore.sh`'s hardcoded volume names
   silently produced wrong, empty backups against `compose.dev.yml`
   — a combination the scripts' own documentation offered as a
   supported usage example, never actually tested until this unit.

## Lessons learned

- A script's own documented "usage example" is a claim that needs the
  same live verification as anything else — this bug lived in exactly
  the combination `scripts/backup.sh`'s own header comment held up as
  a legitimate way to use it, undiscovered because no prior unit
  happened to actually run that specific combination.
- `set -e` is not a universal safety net — it only helps when the
  command that fails actually returns a non-zero exit code, and this
  unit found a real case (`podman volume export` on a name absent
  from `podman volume ls`) where a Podman subcommand's own exit code
  didn't reliably signal the failure a human would expect. Explicit
  existence checks (`podman volume exists`) are more trustworthy than
  assuming a subcommand fails the way its name suggests it should.
- Testing "the same thing, but starting completely fresh" surfaces
  different bugs than testing "the same thing repeatedly against
  already-established state" — every one of this session's prior
  `compose.dev.yml`-adjacent tests had, by convenience or accident,
  avoided the exact combination this unit's insistence on a genuinely
  fresh clone happened to exercise for the first time.
- A CSRF token is valid only in the sense that it matches the current
  session — but a page with multiple forms has multiple tokens, and
  grabbing "the first one" isn't the same as grabbing "the one that
  belongs to the form being submitted" from a human's perspective,
  even though Django itself doesn't distinguish them. Worth being
  precise about which token belongs to which form when scripting a
  real form submission, not just grabbing whichever one a naive regex
  finds first.

## Git

Branch: `feature/clean-environment-test`
Commit: `6b9e25c`
Merged to `main`: `ecfee3a` (regular merge commit, PR #76 — CI green:
`test` + `dependency-audit` both pass; Sourcery reviewed this PR too
but hit its free-tier review-budget limit before producing line-level
comments, same as PR #74 — only a summary/reviewer's guide, no
findings; this unit's own two full live lifecycle tests already
served as the equivalent scrutiny)

## Next

**Phase 13 (Final production audit) is now fully complete** (both
units: production readiness audit, clean-environment end-to-end
test). Next is Phase 14 — Documentation and handoff:
`docs/ADMIN_GUIDE.md`, `docs/DEVELOPER_GUIDE.md`, final repository
cleanup.
