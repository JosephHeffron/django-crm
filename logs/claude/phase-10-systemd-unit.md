# PHASE 10: PRODUCTION SYSTEMD UNIT (UNIT 1)

Started: 2026-09-16
Ended: 2026-09-16

## Objective

First of two Phase 10 units, per the roadmap: a production systemd
unit for the Podman Compose stack, per `docs/ARCHITECTURE.md`'s
"Production deployment architecture" and ADR 0004's "one systemd
unit" decision.

## Files created / changed

- `docs/decisions/0005-rootless-systemd-deployment.md` — new ADR.
  Pins down *how* the one systemd unit ADR 0004 already committed to
  actually runs Podman: as a systemd **user** unit under a dedicated
  non-root deployment account, not a root-owned system unit. Written
  before implementation, per `CLAUDE.md`'s documentation rules.
- `systemd/crm.service` — new. `Type=oneshot`/`RemainAfterExit=yes`,
  `ExecStart`/`ExecStop` wrapping `podman-compose -f compose.prod.yml
  up -d`/`down`, `WorkingDirectory=%h/django-crm`,
  `WantedBy=default.target` (the correct target for a user unit).

## Commands

$ Live test under `systemctl --user` on this Fedora workstation,
  using a throwaway `crm-test.service` (adjusted `WorkingDirectory` to
  this repo's real path, `ExecStart`/`ExecStop` pointed at a throwaway
  `compose.dev.verify.yml` + `.env.compose-verify`, matching the
  established throwaway-verification pattern from every prior
  container-related unit — never the real `.env`):
  - `systemctl --user daemon-reload` + `systemctl --user start
    crm-test.service` — succeeded, `podman-compose up -d` ran to
    completion as the unit's `ExecStart`.
  - `systemctl --user status crm-test.service` — `Active: active
    (exited)`, confirming `Type=oneshot`/`RemainAfterExit=yes` behaves
    exactly as intended: the unit reports "active" even though its
    `ExecStart` process itself already exited (by design — it started
    detached containers and returned).
  - `podman ps -a` — all three containers (`db`, `web`, `caddy`)
    actually running and healthy, not just the systemd unit claiming
    success.
  - `curl -sk https://localhost:8443/accounts/login/` — real `200`,
    the full stack reachable end-to-end through the systemd-managed
    Caddy.
  - `journalctl --user -u crm-test.service` — transparently showed
    real container log lines (Caddy's TLS handshake, gunicorn's access
    log) interleaved with the unit's own systemd-level messages,
    confirming journald integration works without any extra
    configuration.
  - `systemctl --user stop crm-test.service` — ran `ExecStop`
    (`podman-compose down`) successfully; `podman ps -a` afterward
    showed zero containers — a real, verified teardown, not just an
    assumption that `ExecStop` would work because `ExecStart` did.
  - `systemctl --user enable` / `is-enabled` / `disable` /
    `is-enabled` — confirmed the `[Install]` section's
    `WantedBy=default.target` correctly creates/removes the
    `default.target.wants/` symlink.
  - Cleaned up: removed the throwaway test unit file, ran `daemon-
    reload`, removed the throwaway env/compose files, named volumes,
    and the throwaway-built `django-crm_web:latest` image.

$ `ruff check .` / `ruff format --check .` / `bandit -r apps config
  -q` / `pip-audit` / `manage.py check`
Result: PASS — pre-existing B106 test-fixture findings only from
bandit (unrelated, same baseline as every prior unit).

$ `python manage.py test` (full suite)
Result: PASS — 296 tests (unchanged — this unit is a systemd unit +
ADR, no application code).

## Tests

`python manage.py test` — 296 passed, 0 failures.

## Decisions

- **Systemd user unit, not a system unit** — the real decision this
  unit makes, recorded in ADR 0005 rather than only in this log,
  since it's architecturally significant: it's what keeps production
  Podman rootless, consistent with every environment this project has
  actually run and verified Podman in so far, and it's what keeps
  `docs/PRODUCTION_CONFIG_REVIEW.md`'s existing Caddy-as-root
  deferral reasoning (rootless Podman's user-namespace isolation)
  actually true in production, not just in local testing.
- Rejected Podman Quadlet for now — ADR 0004 already committed to
  "one systemd unit" wrapping the existing, already-tested
  `podman-compose` stack; adopting Quadlet's per-container unit model
  would be a real architecture change from what's documented, not
  justified by any concrete requirement the simpler model doesn't
  already meet.
- `TimeoutStartSec=600` — generous specifically because the real
  first-boot case on the Raspberry Pi involves a native (non-emulated)
  ARM64 image build, not just starting already-built containers; a
  tight timeout tuned to this workstation's fast rebuild-from-cache
  case would be the wrong thing to ship.

## Errors

None. The unit's mechanics worked correctly on the first full test
cycle (start → verify running → verify reachable → verify logs → stop
→ verify torn down → enable/disable) — no bugs found or fixed in this
particular unit, unlike most prior infra units.

## Lessons learned

- `Type=oneshot` + `RemainAfterExit=yes` is the correct systemd
  pattern for a unit that launches an already-daemonizing process
  (`podman-compose up -d` returns once containers are detached) —
  confirmed directly via `systemctl status` showing `active (exited)`
  while the actual containers kept running, not inferred from systemd
  documentation alone.
- A systemd **user** unit's `journalctl --user -u <unit>` integration
  with Podman's own container logging requires no extra configuration
  — container stdout/stderr (already routed through `conmon`/journald
  by Podman itself) shows up directly in the unit's own journal
  output, verified live rather than assumed.
- Testing a systemd unit's *mechanics* (does `Type=oneshot` behave as
  expected, does `ExecStop` actually tear things down, does
  `[Install]` work) doesn't require the target hardware or a real
  systemd *system* unit — a throwaway `systemctl --user` unit on this
  development workstation exercises the same systemd primitives the
  real Raspberry Pi deployment will use, just pointed at throwaway
  data. The one thing genuinely deferred to real hardware is whether
  `loginctl enable-linger` behaves identically on the Pi's OS — not
  tested here, out of scope until hardware exists.

## Git

Branch: `feature/systemd-unit`
Commit: `c9c9fd7`
Merged to `main`: `7d791be` (regular merge commit, PR #62 — CI green:
`test` + `dependency-audit` both pass; the repo is private now, so
Sourcery doesn't review it — expected, not an error, and this unit's
own live `systemctl --user` verification already served as the
equivalent scrutiny)

## Next

Phase 10 unit 2 — a safe, non-destructive deployment script with
rollback (`scripts/deploy.sh`, already named/referenced in
`CLAUDE.md`'s "DEPLOYMENT RULES" and `docs/ARCHITECTURE.md`'s
"Production deployment architecture"). Phase 10 is not yet complete —
`docs/ROADMAP.md` stays unchecked until unit 2 also merges.
