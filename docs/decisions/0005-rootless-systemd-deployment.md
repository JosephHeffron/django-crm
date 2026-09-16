# 0005 — Rootless Podman under a systemd user unit for production

## Context

ADR 0004 already decided the production stack runs as three Podman
containers supervised by "one systemd unit," per
`docs/ARCHITECTURE.md`'s "Production deployment architecture"
(`systemd/crm.service`). What it didn't pin down is *how* that
systemd unit runs Podman: as a root-owned system service managing
rootful containers, or as a non-root user's systemd session managing
rootless containers — the same model this project has used throughout
local development (Fedora workstation) and every live verification
done so far in Phases 7-9.

This matters beyond style: `docs/PRODUCTION_CONFIG_REVIEW.md` (Phase 8
unit 2) already found that Caddy's official image runs as root
*inside* its own container, and explicitly deferred fixing that,
reasoning that "rootless Podman's user-namespace isolation already
narrows the real-world blast radius of running as root inside the
container." That reasoning is only true in production if production
*actually* runs rootless Podman — if the real Raspberry Pi deployment
ran rootful Podman instead, that already-accepted trade-off would be
re-opened without anyone deciding to re-open it.

## Alternatives considered

- **Rootful Podman under a system-level systemd unit**
  (`/etc/systemd/system/crm.service`, running as root). Rejected: this
  is the one architecture where Caddy's root-inside-container default
  (Phase 8 unit 2) would actually mean root-on-the-host-equivalent
  privilege if a container escape ever occurred — exactly the risk
  Phase 8's own reasoning assumed wasn't present. Also inconsistent
  with every other environment this project has run Podman in so far
  (Fedora workstation dev, every Phase 7-9 live verification).
- **Podman Quadlet** (`.container`/`.network`/`.volume` unit files,
  Podman's newer systemd-integration mechanism, generating one
  systemd unit per container). Rejected for now: ADR 0004 already
  committed to "one systemd unit" wrapping the existing
  `podman-compose` stack, and Quadlet would mean three-plus new unit
  files plus splitting `compose.prod.yml`'s existing, already-tested
  configuration across them — a real architecture change from what's
  already documented and decided, not a drop-in choice, and not
  justified by a concrete requirement `docs/ARCHITECTURE.md`'s
  simpler single-unit model doesn't already meet.
- **A rootless *system* unit** (`/etc/systemd/system/crm.service`,
  still running as root but with `podman run --userns=keep-id` or
  similar per-container flags to approximate rootless). Rejected:
  more complex than simply running the whole unit as an unprivileged
  user's systemd *user* session, which gets genuine rootless behavior
  (the same `podman`/`podman-compose` invocation already used and
  tested throughout this project) for free, with no extra flags to
  keep in sync with `compose.prod.yml`.

## Decision

`systemd/crm.service` is a systemd **user** unit, run by a dedicated
non-root deployment account on the Raspberry Pi (not the interactive
login user, not root), with that account's session kept alive across
reboots via `loginctl enable-linger <user>` — the standard, documented
mechanism for a systemd user unit to start at boot without requiring
an active login.

## Reason

Keeps production on the exact same rootless Podman model already used
and verified throughout local development and every prior phase's
live testing (Phases 7-9) — no second, untested "how Podman actually
runs in production" configuration to maintain alongside the one
that's been exercised all along. Preserves the user-namespace
isolation `docs/PRODUCTION_CONFIG_REVIEW.md` already relied on to
defer the Caddy-as-root finding, rather than silently invalidating
that reasoning by deploying rootful. Matches ADR 0004's "one systemd
unit" decision exactly — this ADR only pins down *how* that one unit
runs Podman, not whether there should be more than one.

## Consequences

- The Raspberry Pi needs a dedicated non-root system user for this
  deployment (not documented/created here — that's an operational
  setup step for whenever real hardware exists, Phase 13/14's
  territory) with `loginctl enable-linger` run once for it.
- `systemd/crm.service` uses `WantedBy=default.target` (the correct
  target for a user unit) rather than `multi-user.target`, and
  `%h`-relative paths for the repository location, not an absolute
  root-owned path.
- `scripts/deploy.sh` (Phase 10 unit 2) invokes `systemctl --user`,
  not plain `systemctl`, when interacting with this unit.
- This project's rootless-Podman reasoning (SELinux `:Z` labels
  documented in `compose.dev.yml`/`compose.prod.yml`, the Caddy-as-root
  deferral in `docs/PRODUCTION_CONFIG_REVIEW.md`) now applies uniformly
  across dev, live verification, and production — no environment where
  it silently stops being true.

## Date

2026-09-16
