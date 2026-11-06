# 0022 — Caddy on the host network, so it sees real client addresses

## Context

The login rate limit (ADR 0020) counts failed sign-ins per client
address and per username. It finds the client address as the **last**
`X-Forwarded-For` entry, which is the peer Caddy itself spoke to.

That holds only if Caddy's peer is the visitor. In `compose.prod.yml`
until now, Caddy sat on the compose network with `ports: 80:80, 443:443`.
Under **rootless** Podman (ADR 0005), a published port on a compose
(bridge) network is forwarded by `rootlessport`, a userspace proxy that
rewrites the source of every connection to an address inside the
container network. Podman's own blog describes the effect: containers
on bridge networks cannot see the real source address, which breaks
"IP-based access control, logging, and rate limiting". Podman's
networking documentation lists "pasta + custom network" and
"slirp4netns + port_handler=rootlesskit" as the modes that do **not**
preserve the source address.

So in production every visitor would reach Caddy, and therefore
Django, from the same address. **The per-IP login limit becomes one
bucket for the whole internet.** Ten wrong passwords from anybody would
lock everybody out of signing in for fifteen minutes, over and over,
for as long as somebody keeps trying. That is a denial of service
anyone can trigger with a browser. Phase 22.5 unit 5's spam limit on
`/book/` would fail the same way, against customers.

*Status of this claim: documented upstream, not yet observed on this
project's stack, which has never run on the droplet. The development
workstation would show the same thing, but one person testing from
one address cannot notice it. The verification step in
`docs/ADMIN_GUIDE.md` settles it on the real host.*

## Alternatives considered

- **Podman's pasta port forwarder** (`rootless_port_forwarder = "pasta"`
  in `containers.conf`). This is the upstream fix. It merged in May
  2026 as experimental, is not the default, and needs a newer `passt`.
  Ubuntu 24.04 ships Podman 4.9.3. Not available on the target.
- **slirp4netns with `port_handler=slirp4netns`.** Preserves the
  source, but cannot be used on a user-defined network, so Caddy could
  no longer reach `web` by name. It would also need host-loopback
  access configured to reach a published port. More moving parts than
  the host network, for the same result.
- **Socket activation.** Systemd owns the listening sockets and hands
  them to Caddy, so the source is preserved and the container can stay
  on the compose network. It is the most isolated option, but it needs
  socket units, Caddyfile `bind fd/…` addresses, and a different start
  path from the one `crm.service` and `deploy.sh` use. Worth revisiting
  if the host network ever proves to be a problem.
- **PROXY protocol.** Needs something in front of Caddy to speak it.
  There is nothing in front of Caddy.
- **Caddy as a host package, outside Podman.** Runs as a system service
  under root, and departs from ADR 0004 for no gain over the host
  network.
- **Drop the per-IP limit and keep only per-username.** Removes the
  lockout, but lets one address try every username without limit, and
  leaves `/book/` with nothing to count. A weaker control is not a fix.

## Decision

**In `compose.prod.yml`, Caddy runs with `network_mode: host`. Django
is published on `127.0.0.1:8000` only, and the production Caddyfile
proxies to `127.0.0.1:8000`.**

- With the host network, Caddy itself accepts each visitor's
  connection on 80 and 443, so the address it appends to
  `X-Forwarded-For` is the visitor's own. `apps/users/throttle.py`
  needs no change.
- Caddy is still rootless. Binding 80 and 443 still relies on the
  `net.ipv4.ip_unprivileged_port_start=80` sysctl the deployment guide
  already sets. `ports:` no longer applies to it and is removed.
- The rewrite moves to the hop between Caddy and Django, where it does
  no harm: Django's `REMOTE_ADDR` was always the proxy, and the client
  address travels in the header.
- **Django's port is bound to the loopback address only.** A bare
  `8000:8000` would put gunicorn on every interface, bypassing TLS,
  the security headers and the private-media rule. A test refuses it.
- **Caddy's admin API is turned off** (`admin off`). It listens on
  `localhost:2019` by default, which on the host network is the
  server's own loopback, where any local account could reconfigure the
  proxy. Nothing uses it, because deploys recreate the container
  rather than reload the config. A test asserts it stays off.
- **The development stack does not change.** `compose.dev.yml` and
  `Caddyfile.dev` keep Caddy on the compose network. On a workstation
  every visitor is the developer, and the host-network layout would
  collide with `manage.py runserver` on port 8000. This is a deliberate
  difference, recorded in `Caddyfile.dev`, and the droplet is where the
  production layout is proven.

## Reason

It is the smallest change that makes the existing limiter correct on
the existing target, with no new component, no new privilege and no
dependency on unreleased Podman features. The two things the host
network newly exposes, Django's port and Caddy's admin API, are each
closed explicitly and each held by a test.

## Consequences

- **Caddy shares the host's network namespace.** It can reach anything
  listening on the host's loopback. That is Django's published port,
  which is what it is for, and nothing else: PostgreSQL publishes no
  port. A future service that listens on the host's loopback should be
  added with this in mind.
- **The firewall still decides what is public.** DigitalOcean's cloud
  firewall allows 22, 80 and 443 only. Django's port is on loopback,
  so it is not reachable from outside even if a firewall rule is wrong.
- **Proof is on the droplet, not here.** The guide's check is
  `ss -tlnp` showing the process that owns ports 80 and 443 is `caddy`,
  not `rootlessport`. A rootless Caddy behind a port forwarder would
  show the forwarder.
- **ADR 0016's site blocks are unchanged.** Only the upstream address
  changes, from `web:8000` to `127.0.0.1:8000`, and the `/book/*` route
  unit 5 adds uses the same address.
- If Podman's pasta forwarder becomes the default on the target, this
  can be revisited. The host network is not wrong then, just no longer
  necessary.

## Date

2026-11-06
