# 0004 — Podman + Caddy for containerized deployment

> **Still current, but the host changed.** This ADR was written when the
> production target was a Raspberry Pi 5. That target was dropped on
> 2026-11-02 for an x86-64 Ubuntu VPS
> ([ADR 0015](0015-x86-64-vps-replaces-the-raspberry-pi.md)). The
> decision below stands — none of its reasoning depended on the
> hardware or the architecture — so read "the Pi" as "the server".

## Context

The CRM needs to run reliably on a Raspberry Pi 5 (ARM64), be reachable
over HTTPS, and survive reboots/crashes without manual intervention. It's
operated by a single person, not a team with dedicated ops tooling.

## Alternatives considered

- **Kubernetes / k3s**. Rejected outright by the project's "do not
  overengineer" rule — orchestration, scheduling, and multi-node concerns
  solve problems this single-host, single-maintainer deployment doesn't
  have.
- **Docker + Docker Compose**. Rejected in favor of Podman: Podman is
  daemonless (no persistent root-owned background service), supports
  rootless containers more naturally, and is the container tooling
  already standard on Fedora — one fewer thing to install and secure.
- **Nginx or Traefik as the reverse proxy**. Rejected in favor of Caddy:
  Caddy's automatic HTTPS (via ACME) removes manual certificate management,
  which matters for a single-maintainer project without a dedicated ops
  rotation.
- **Bare-metal deployment (no containers)**. Rejected: containers give a
  reproducible, testable artifact that can be validated on the Fedora
  workstation (via `qemu-user-static` for ARM64) before it ever touches
  the Raspberry Pi, and make rollback a matter of switching images rather
  than untangling an in-place upgrade.

## Decision

Deploy as three Podman containers — Django (Gunicorn), PostgreSQL, Caddy —
orchestrated with `podman-compose`, supervised by a systemd unit on the
Raspberry Pi. Caddy is the only container exposed to the LAN/Internet.

## Reason

Matches the single-host, single-maintainer, ARM64 target while keeping the
architecture as simple as three containers and one systemd unit — no
orchestration layer, no service mesh.

## Consequences

- All three container images must support `linux/arm64`; this is verified
  on the Fedora workstation via `qemu-user-static` before deployment
  (ARM64 phase).
- Only Caddy terminates HTTPS; Django and PostgreSQL are only reachable on
  the internal Podman network — this is the security boundary documented
  in `docs/ARCHITECTURE.md`.
- systemd (not a container orchestrator) is responsible for "start on
  boot" and "restart on crash" — this is the extent of the automation
  needed at this scale.

## Date

2026-09-10
