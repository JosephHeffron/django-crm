# AI development operating procedures

This document holds the detailed mechanics behind the rules stated in
`CLAUDE.md`: log formats, checklists, and concrete allow/deny examples.
`CLAUDE.md` is the permanent contract; this file is the how-to.

## Phase logging

Every development phase gets a dedicated log at
`logs/claude/phase-NN-<slug>.md`. Never overwrite a previous phase's log.

Template:

```markdown
# PHASE NN: <TITLE>

Started: YYYY-MM-DD HH:MM
Ended:   YYYY-MM-DD HH:MM

## Objective
<what this phase set out to do>

## Files created / changed
- path/one
- path/two

## Commands

$ <command>
Result: <PASS/FAIL and a one-line summary>

(Repeat for each significant command. Explain *why* it was run, what it was
expected to do, and whether it succeeded — not just a raw transcript.)

## Tests
<test command>
Result: <N passed / failed, summary>

## Decisions
- <decision made and why, or "see docs/decisions/000N-*.md">

## Errors
- <what failed, why if known, how it was resolved, remaining implications>

## Git
Branch: <branch>
Commit: <hash, or "not yet committed">

## Lessons learned
- What worked?
- What failed?
- What assumption was wrong?
- What should be automated or documented?
- What should be avoided in future phases?

## Next
<the exact next recommended step>
```

## Session transcripts

Archived under `logs/claude/sessions/YYYY-MM-DD_HHMM_<slug>.md`. Sanitize
before saving: never write actual secret values, tokens, or credentials
into a transcript — redact as `[REDACTED]`.

## Git operation logs

`logs/git/commits.md` — one entry per meaningful commit:

```
YYYY-MM-DD
Branch: feature/<name>
Commit: <short hash>
Message: <first line of commit message>
Tests: <N passed>
Migration: <migration filename, or "none">
Reviewer: Human
Status: READY
```

`logs/git/branches.md` — one line per branch created/merged/deleted (Claude
never deletes a branch without explicit instruction — record who asked).

`logs/git/releases.md` — one entry per tagged release (once releases start,
in a later phase).

## Failure log

One file per significant failure: `logs/failures/failure-YYYYMMDD-HHMMSS.md`

```markdown
## Problem
## Environment
## Command
## Output summary
## Root cause
## Resolution
## Preventive action
```

## System change log

`logs/system/` — one entry per significant environment change (package
installed, service version changed, systemd unit changed, firewall rule
added):

```
YYYY-MM-DD
ACTION: <what changed>
COMMAND: <command run>
PURPOSE: <why>
RESULT: <SUCCESS/FAILURE>
```

## Before/after state capture

At the start and end of each phase, record in the phase log: Git commit,
Git status, Python version, Django version, Podman version, PostgreSQL
version, OS version. This makes it possible to bisect what changed when
something unexpectedly breaks later.

## Session start checklist (mechanical form of CLAUDE.md's procedure)

1. `cat CLAUDE.md docs/PROJECT_STATE.md docs/ROADMAP.md`
2. Read the most recent file in `logs/claude/` and `docs/sessions/`.
3. `git status && git branch --show-current && git log --oneline -10`
4. State: what's done, what's next, before touching anything.

## Session close checklist (mechanical form of CLAUDE.md's procedure)

1. Run the relevant test command(s); paste actual results, not assumptions.
2. `git diff` / `git status`.
3. Update `docs/PROJECT_STATE.md`.
4. Write/update `logs/claude/phase-NN-*.md`.
5. Update `CHANGELOG.md` if the change is release-meaningful.
6. Update/create ADRs in `docs/decisions/` for any architectural decision.
7. State remaining work and the exact next step.
8. State the commit hash if one was created; state explicitly that nothing
   was pushed unless it was, and that was authorized.

## Bash allow/deny examples

These are illustrative; the enforced list lives in `.claude/settings.json`.

Allowed without prompting: `git status`, `git diff`, `git log`, `git
branch`, `python`, `pytest`, `ruff`, Django management commands that are
read-only or additive (`check`, `test`, `makemigrations --check`,
`migrate`), `podman build`, `podman compose up/ps/logs`, `systemctl
status`, `journalctl`, `curl` against local development services.

Requires explicit approval regardless of any allowlist: `git push
--force`, `git reset --hard`, `rm -rf`, `DROP DATABASE`, `DROP TABLE`,
`TRUNCATE`, `fdisk`, `mkfs`, `dd`, `shutdown`, `reboot`, firewall
flush/disable, SELinux disable.

## Sudo policy examples

Routine (allowed): `dnf install/update` packages, `systemctl
status/start/stop/restart` on this project's services, `journalctl`
access, firewall configuration for this project, directory
ownership/permissions for this project, installing Podman/`qemu-user-static`,
Podman configuration.

Never: delete unrelated system data, recursive permission/ownership changes
across the filesystem, disable SELinux, disable the firewall, modify
unrelated services, destroy partitions, reformat disks, delete user
accounts, modify SSH configuration without explicit authorization, change
bootloader configuration, or run a destructive command merely to resolve an
error. Stop and explain before any unexpected or destructive sudo use.
