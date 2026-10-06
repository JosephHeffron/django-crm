# PHASE 17.5 STEP 10: SETTINGS

Started: 2026-10-06
Ended: 2026-10-06

## Objective

The Settings side of the reference design (ADR 0010): a hub behind the
gear, Company Management that can actually set what someone reaches, an
activity log that can put a change back, a Customize hub, and What's
New.

## Files created / changed

- `apps/core/views.py` — `SettingsHubView` (cards filtered to what the
  person may open; needs a role, because every page it links to does —
  a hub of doors you can't open is worse than no hub), `CustomizeView`,
  `ActivityLogView`, `ActivityUndoView` (POST only), `WhatsNewView`.
- `apps/crm/undo.py` — putting a recorded edit back. The log stores
  changes as **text**, which is enough to restore a name or a phone
  number exactly and not enough to restore a date or a linked record
  without guessing, so an entry is undoable only when every field it
  touched is text-like, and the page says plainly when one isn't. Two
  further rules, because this writes to a customer's record: a field is
  only put back if it still holds what that change set (otherwise
  somebody's later work would be thrown away), and **the undo is itself
  recorded**, so the log tells the whole story.
- `apps/core/changelog.py` — What's New reads `CHANGELOG.md`, so a
  release note is written once rather than twice. It parses the Keep a
  Changelog shape and nothing cleverer; anything it can't read is
  skipped, so a malformed heading costs one release, not the page.
- `apps/users/forms.py` + `views.py` — `MemberAccessForm`: the Owner
  sets someone's role and whether they can sign in, which was
  admin-only until now. One role apiece, matching how the rest of the
  app asks the question (ADR 0008). Turning off sign-in keeps every
  record they ever made.
- Templates: `settings_hub.html`, `customize.html`, `activity_log.html`,
  `whats_new.html`, and the access section on a teammate's page.
- `apps/core/navigation.py` — the gear menu gains Settings, Customize
  (now its own hub rather than pointing at the service list), Activity
  log and What's new.
- Docs: USER_GUIDE (Settings, Company management, Customize, the
  activity log and what undo will and won't do), PERMISSIONS (five new
  rows).
- Tests: `apps/core/tests/test_settings_hub.py` (24) — the hub per role
  and every card opening, Customize, the changelog parser including a
  malformed release and a missing file, the log listing changes, undo
  restoring one field and several, refusing when somebody has changed
  it since, refusing a creation, refusing a field it can't restore
  exactly, and recording itself; and member access changing a role,
  leaving only one, clearing it, and keeping records when sign-in is
  turned off.

## Decisions

- **Undo is narrow and says so.** Text fields only, nothing changed
  since, and recorded. The alternative — guessing a date or a row from
  its printed form — would quietly write the wrong value into a
  customer's record.
- **What's New reads the changelog** rather than a new model. One place
  to write a release note.

## Verification

$ `manage.py test` — 775 tests, OK (751 before, 24 new). No migrations.
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean.
$ Playwright under production settings, 26 checks, zero CSP violations:
  the hub and every card opening; Customize; What's new with its newest
  release open; editing a customer, finding it in the log, pressing
  Undo and seeing the old value back; setting a teammate's role and
  getting it back; a rep seeing 4 cards of 9 and refused the two
  Owner-only pages; phone light and dark. The audit entries and the role
  change made during the check were reverted afterwards.

## Errors

- The check script submitted `form button[type=submit]`, which matches
  the top bar's theme toggle before the page's own form — the same trap
  as steps 5 and 6. Scoped to the button's text.

## Git

Branch: `feature/restyle-settings`
Commit: pending
Merged to `main`: pending

## Next

Step 11 — the remaining pages and a responsive pass.
