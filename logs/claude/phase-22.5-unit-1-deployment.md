# PHASE 22.5 UNIT 1 (CONTINUED): DEPLOYMENT GUIDE, BACKUP ALERTING, REAL CLIENT ADDRESSES

Started: 2026-11-06
Ended:   2026-11-06 (code; the droplet is the real test)

Two PRs, the second stacked on the first:

1. `security/real-client-ip`: ADR 0022, Caddy on the host network.
2. `feature/unit1-deployment`: the Ubuntu guide, backup alerting, and
   full deploys that check Caddy.

The earlier part of unit 1 (accounts, owner-set passwords, the
Raspberry Pi target dropped) is in `phase-22.5-unit-1-accounts.md`.

## The thing worth reading

**The login rate limit would have locked everybody out.** ADR 0020
counts failed sign-ins per client address, taken from the last
`X-Forwarded-For` entry, which is the peer Caddy spoke to. Under
rootless Podman, a port published on a compose network is forwarded by
`rootlessport`, which rewrites the source of every connection. Podman's
blog says outright that this breaks rate limiting, and its networking
docs list "pasta + custom network" and "slirp4netns +
rootlesskit" as the modes that do not preserve the source address. So
every visitor would have shared one bucket, and ten wrong passwords
from anyone would have kept the whole team out of the CRM for fifteen
minutes at a time, as often as someone cared to repeat it.

Nobody would have seen it on the workstation, because one person
testing from one address cannot. It came out of writing the
deployment guide, while checking how a rootless Ubuntu host differs
from the workstation. The upstream fix (`rootless_port_forwarder =
"pasta"`) merged in May 2026 as experimental, and Ubuntu 24.04 ships
Podman 4.9.3.

The owner chose to fix it now (asked mid-session). ADR 0022 records
the decision: production Caddy uses `network_mode: host`, Django is
published on `127.0.0.1:8000` only, the production Caddyfile proxies to
`127.0.0.1:8000`, and Caddy's admin API is off, because on the host
network it would have listened on the server's own loopback. The dev
stack is unchanged on purpose. On a workstation every visitor is you,
and the host-network layout collides with `runserver` on port 8000.

**Status: documented upstream, not observed.** The guide's step 7
(`ss -tlnp` must show `caddy`, not `rootlessport`, on 80 and 443) is
what proves it on the droplet.

## Also found

- **Ubuntu 24.04's `podman-compose` is 1.0.6**
  (packages.ubuntu.com). Support for honouring `depends_on`
  conditions arrived in 1.3.0 (the openSUSE package changelog), and
  users report 1.0.6 treating `service_healthy` as `service_started`.
  `compose.prod.yml` relies on those conditions. The guide installs
  podman-compose with pipx, pinned to the workstation's version and at
  least 1.3.0. `crm.service` hard-coded `/usr/bin/podman-compose`,
  which a pipx install does not provide (audit F-VPS-2); it now runs
  `/usr/bin/env podman-compose` with
  `PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin`.
- **A full deploy never asked Caddy** (found in the previous session
  and recorded then). `verify_health` checks only `db` and `web`.
  Fixed here: see below.
- **Two stale lines** corrected while passing: `docs/ADMIN_GUIDE.md`
  still listed "no Content-Security-Policy header" as a limitation
  (CSP shipped in Phase 16, ADR 0007), and `docs/VPS_PLAN_SUMMARY.md`
  still promised "a password reset that works" (ADR 0021 replaced
  it).

## What was built

### PR 1 — ADR 0022

- `compose.prod.yml`: `caddy` has `network_mode: host` and no
  `ports:`; `web` has `ports: ["127.0.0.1:8000:8000"]`.
- `Caddyfile`: a global options block, `{ admin off }`, first in the
  file; `reverse_proxy 127.0.0.1:8000`; header comments updated.
- `Caddyfile.dev`: unchanged config, plus a comment recording the
  deliberate difference.
- ADR 0022; amendment notes on ADRs 0016 and 0020;
  `docs/ARCHITECTURE.md` security boundaries; CHANGELOG (Security);
  ROADMAP.
- `strip_comments` moved from `test_private_media.py` to
  `apps/core/tests/_caddy.py`, so both modules share it.
- `apps/core/tests/test_client_address.py`, 9 tests:
  - Caddy on the host network with no ports.
  - Django published on `127.0.0.1:8000` and nothing else.
  - The database not published.
  - A test that the port reader really sees a public binding.
  - The live Caddyfile proxies to loopback and never to `web:8000`.
  - The admin API is off in the first block.
  - From `caddy adapt` (CI only): `admin.disabled` is true, every
    production upstream is `127.0.0.1:8000`, and dev keeps `web:8000`.

### PR 2 — the rest of unit 1

- **`scripts/backup.sh`:** `ping_monitor` requests `BACKUP_PING_URL`
  with `curl -fsS --max-time 10 --retry 5`, only after `restic forget`
  succeeds.
  - Without `RESTIC_REPOSITORY`, it warns and never pings.
  - An unreachable monitor warns and does not fail the backup.
  - The URL is never printed.
  - `.env.example` documents the setting.
- **`scripts/deploy.sh`:**
  - `verify_crm` fetches `https://$CRM_HOST/health/` through Caddy.
  - `verify_caddy` is `verify_crm && verify_website`.
  - `wait_for_caddy` retries it (`CADDY_CHECK_RETRIES`, default 24, at
    `HEALTH_CHECK_INTERVAL`, now overridable).
  - `restart_and_verify` requires it after `db` and `web` are healthy.
  - `status` reports all of them and fails if any fail.
  - `website_host` became `env_value`, which reads one setting from
    `.env` in a subshell. Its first draft used `eval` for indirect
    expansion; that was replaced with an explicit `case` of the two
    allowed names, so nothing in it is ever evaluated as code.
- **`systemd/crm.service`:** `PATH` and `/usr/bin/env`, as above.
- **`docs/ADMIN_GUIDE.md`:** *First-time deployment* rewritten for
  Ubuntu 24.04 on DigitalOcean in eleven steps. Covered:
  - Droplet, reserved IP, cloud firewall.
  - apt packages, swap, unattended upgrades, the port sysctl.
  - The `crm` account without sudo, with its subuid/subgid check,
    lingering and SSH key. SSH in as `crm`, never `su`, because
    `systemctl --user` needs that user's own session.
  - podman-compose through pipx; DNS for `crm` and `new`.
  - `.env`, including a no-spaces check that sources it the way the
    backup does.
  - Start, verification including the `ss` check, two Owner accounts.
  - B2, healthchecks.io and the timer; the follow-up timer; the restore
    drill.
  - A section on what the first run is most likely to correct.
- **Tests:**
  - The deploy test setup moved to `apps/core/tests/_deploy.py` and is
    shared by the website-only tests and the new
    `apps/core/tests/test_deploy_script.py` (12 tests): full deploys,
    status, the certificate-check reader, and `crm.service`.
  - `apps/core/tests/test_backup_monitoring.py` (8 tests) runs the real
    `backup.sh` with `podman`, `restic` and `curl` stubbed, logging
    every call in order to one shared file.

## Commands

$ apt package versions, podman-compose history, Podman networking
Result: web research. Ubuntu noble has podman-compose 1.0.6 and Podman
4.9.3. podman-compose 1.3.0 added `depends_on` conditions. Podman
documents that `rootlessport` does not preserve the source address on
custom networks. healthchecks.io's free plan has 20 checks with email
alerts.

$ PYTHONPATH=/tmp/djstub:. python3 -m unittest apps.core.tests.test_client_address apps.core.tests.test_website apps.core.tests.test_website_fast_paths apps.core.tests.test_backup_monitoring apps.core.tests.test_deploy_script apps.core.tests.test_backup_integrity
Result: all pass. The `caddy adapt` classes skip here, as before.
`test_backup_integrity` was included because it parses
`compose.prod.yml`.

First-run failures, both in the tests rather than the scripts:
- `-fsS` is one combined flag, and the test looked for `-f` alone.
- A certificate-check assertion missed `-kfsS` (mutation below), so
  `skips_certificate_checks` now reads combined short flags and has a
  test of its own.

Mutations, each applied to a copy and the module rerun. Every one was
caught by the test meant to catch it:

| Broken | Caught by |
|---|---|
| Django published as `8000:8000` | `test_django_is_published_on_loopback_and_nowhere_else` |
| Caddy back on the bridge with ports | `test_caddy_is_on_the_host_network` |
| `admin off` removed | `test_the_admin_api_is_off` |
| proxy back to `web:8000` | `test_the_crm_proxies_to_the_loopback_port` |
| PostgreSQL published | `test_the_database_is_not_published_at_all` |
| ping sent before the push | three backup tests |
| ping sent when local-only | `test_a_local_only_backup_never_pings_and_says_why` |
| URL echoed | `test_the_url_is_never_printed` |
| ping failure made fatal | `test_an_unreachable_monitor_does_not_fail_a_good_backup` |
| Caddy check dropped from the deploy | four full-deploy tests |
| website dropped from the Caddy check | two full-deploy tests |
| `curl -kfsS` in the CRM check | the healthy-deploy test, after the reader fix |
| `curl -kfsS` in the website check | the healthy-deploy and website-only tests |
| `/usr/bin/podman-compose` restored | both `crm.service` tests |

$ sh -n scripts/deploy.sh scripts/backup.sh
Result: OK.

$ ruff check apps/ && ruff format --check apps/
Result: OK (local ruff 0.16.9; CI's 0.17.3 is authoritative).

**Not run here:** the Django suite, `caddy adapt`, Podman and
podman-compose. CI covers the first two. Only the droplet covers the
rest.

## After review and CI
- **Sourcery on #208, eight threads, all answered and resolved.**
  Changed: each login count is now read and written under a PostgreSQL
  advisory lock per key (`throttle._serialize`), because three workers
  could read the same count and both write N + 1. The port check fails
  closed on any spelling of `ports`, and the Caddy test now asks which
  handler *answers* a request, not only which handlers exist (`first_answer`
  in `apps/core/tests/_caddy.py`). Kept, with the reason in ADR 0022:
  a process on the droplet itself can reach Django without Caddy.
  Commit `a73c26d`.
- **CI then failed, with two errors in the new concurrency tests,
  not in the code.** It was a `TransactionTestCase`, whose end-of-test flush
  truncates every table, and PostgreSQL refused: the retired
  `crm_deal` table (ADR 0012) still references `auth_user`. Now an
  ordinary `TestCase` whose threads commit on connections of their own,
  clearing the cache the same way. Commit `43e6c61`.
- CI: #208 **1,522 tests, OK**; #209, after updating from `main`,
  **1,542, OK**. Both run in about fifteen minutes, as before.

## Decisions
- ADR 0022: host-network Caddy, chosen by the owner over fixing it
  later on the droplet or weakening the limit to per-username only.
- Healthchecks.io is recommended, but the code is generic: any service
  that alerts on a missing HTTP request works. Success pings only. A
  `/fail` signal is specific to healthchecks.io, and the dead man's
  switch already covers failures within the grace time.
- The deploy account has no sudo. The plan said "with sudo", but the
  account that runs internet-facing containers should not be able to
  become root (ADR 0005), and root over SSH with a key covers system
  setup.
- `env_value` uses an explicit list rather than indirect expansion.

## Git
Branches: `security/real-client-ip`, then `feature/unit1-deployment`
on top of it. Commits: `1cfefdc`, `a73c26d` and `43e6c61` (#208, merged
as `74abbfa`); `3fb98e6` (#209, merged as `3c03030`).

## Lessons learned
- **Read the platform, not only the repo.** The repo was internally
  consistent. The breakage was in how Ubuntu packages podman-compose
  and how rootless Podman forwards ports, and both were found by
  reading upstream documentation before writing the guide.
- **A security control can be its own denial of service.** A per-IP
  limit is only as good as the IP. The test suite could not have
  caught this, because every test request comes from one address on
  purpose.
- **Combined short flags defeat naive argument checks.** This bit
  twice in one session (`-fsS`, then `-kfsS`). Read flags as clusters.
- **No `TransactionTestCase` in this repository.** The retired tables
  block its flush. Threads in an ordinary `TestCase` get their own
  connections, which commit.

## Next
1. ~~CI on both PRs, then merge the IP fix first.~~ Done, 2026-11-06.
2. Owner: DigitalOcean, Backblaze and healthchecks.io accounts; Wix
   DNS for `crm` and `new`; the real `.env` check.
3. Unit 2, provisioning, by following the guide. Correct the guide in
   the same PR as whatever the droplet disagrees with, starting with
   step 7's `ss` check.
4. Unit 3: the restore drill before real data.
