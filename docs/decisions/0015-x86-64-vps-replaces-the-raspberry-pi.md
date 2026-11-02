# 0015 — An x86-64 VPS replaces the Raspberry Pi 5 as the deployment target

*(Number reserved for this decision by `docs/VPS_DEPLOYMENT_PLAN.md`'s
ADR table.)*

## Context

This project was built to run on a Raspberry Pi 5 on the owner's own
network: ADR 0004 chose Podman and Caddy, ADR 0005 chose rootless
systemd user units, and every deployment document was written for that
machine. Phase 25 of the roadmap was "real Raspberry Pi hardware
validation", blocked because no Pi was ever bought.

It never was bought, and the plan changed. The CRM and a new public
website will share one **x86-64 Ubuntu 24.04 DigitalOcean droplet**
(2 vCPU, 4 GB, 80 GB), replacing a $85/month RevDek subscription and a
Wix site. The Pi is not a fallback, a staging target, or a later
possibility — it is simply not part of this project.

So the repository carries a second deployment story that will never be
exercised: two review documents (`docs/ARM64_REVIEW.md`,
`docs/ARM64_TESTING.md`), a validation script (`scripts/test-arm64.sh`)
and its `make arm64` target, a blocked roadmap phase, and Raspberry Pi
framing in `CLAUDE.md`, `README.md` and every deployment guide.

**Nothing in the build is ARM-specific.** `docs/VPS_AUDIT.md` F-VPS-7
verified it: no `--platform` flag, no architecture-conditional logic
anywhere. ARM was comments, documents, and one standalone script run by
hand under `qemu-user-static` — never in CI. So removing it removes no
capability.

## Alternatives considered

- **Leave it all in place.** Costs nothing to run, since none of it is
  in CI. But it costs on every read: a contributor — human or AI — who
  believes `CLAUDE.md` will size workers for a 4-core Pi, reach for
  `qemu-user-static`, and write ARM64 notes nobody will act on. The
  audit found the deployment guide already giving Raspberry Pi OS
  package commands for a host that will run Ubuntu (F-VPS-6).
- **Keep the ARM64 documents, marked historical.** Tempting, because
  the emulation work was real and the findings were sound. But they
  describe validating a target that no longer exists, and a document
  marked "historical" still gets found by grep and still has to be
  reasoned about. Git history keeps them available at the exact commit
  where they were true, which is the right place for a record nobody
  needs to act on.
- **Keep the Pi as a documented alternative target.** It would mean
  maintaining and testing two deployment paths for a single-instance,
  one-business CRM, which is precisely what `CLAUDE.md`'s complexity
  rule exists to prevent.

## Decision

The x86-64 VPS is the only deployment target. Specifically:

- **Deleted:** `docs/ARM64_REVIEW.md`, `docs/ARM64_TESTING.md`,
  `scripts/test-arm64.sh`, the `make arm64` target, and roadmap
  Phase 25.
- **Rewritten to the VPS target:** `CLAUDE.md`'s project and stack
  sections, `README.md`, `docs/ARCHITECTURE.md`, and the deployment,
  developer, backup and disaster-recovery guides.
- **Left alone:** `logs/claude/`, `CHANGELOG.md`, and the earlier ADRs.
  Phase logs and changelog entries are records of what happened at the
  time; rewriting them would be falsifying history rather than
  correcting documentation. ADRs 0004 (Podman + Caddy), 0005 (rootless
  systemd) and 0006 (restic to Backblaze B2) **all still stand** — none
  of their reasoning depended on the hardware — and so does ADR 0002
  (PostgreSQL), which mentioned the Pi only as an example of a small
  machine.
- `docs/VPS_AUDIT.md` stays as written. It is a dated audit of the move
  and is accurate as a record of it.

## Reason

A target nobody will deploy to is not documentation, it is
misinformation with a long half-life — and the one thing in the
repository that was genuinely ARM-specific, a hand-run emulation
script, was never part of CI and so was never protecting anything.
Removing it makes every remaining deployment instruction true of the
machine the software will actually run on.

## Consequences

- **The ARM64 review findings are no longer at hand.** They are in git
  history; nothing in the current plan needs them.
- **`qemu-user-static` is no longer a development dependency.** It is
  removed from `CLAUDE.md`'s stack list and the sudo policy's example
  of packages worth installing.
- **`--workers 3` keeps its value and loses its justification.** It was
  chosen for a 4-core Pi; the droplet has 2 vCPU. The comment now says
  so honestly rather than citing hardware that is not involved.
  `docs/VPS_AUDIT.md` F-VPS-8 flags this as an **assumption** —
  three gunicorn workers alongside PostgreSQL and Caddy is plausible
  but untested, with memory the constraint to watch. Changing the
  number without measuring would be the speculative optimisation
  `CLAUDE.md`'s performance rule forbids, so it stays at 3 until there
  is something to measure.
- **The Ubuntu x86-64 deployment work is now unblocked but not done.**
  The port sysctl, `loginctl enable-linger`, subuid/subgid ranges and
  the `podman-compose` path (audit F-VPS-1 through F-VPS-5) are
  separate units, listed in `docs/VPS_AUDIT.md` and sequenced in
  `docs/VPS_DEPLOYMENT_PLAN.md`; this ADR only removes the wrong
  target, it does not write the right guide.
- **If ARM ever returns** — an Apple Silicon workstation, an ARM
  droplet — nothing here prevents it. There is no architecture-specific
  code to undo, which is exactly what F-VPS-7 established.

## Date

2026-11-02
