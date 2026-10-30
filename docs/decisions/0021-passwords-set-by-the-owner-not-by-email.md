# 0021 — Passwords are set by the owner in the app, not reset by email

*(Numbered to avoid `docs/VPS_DEPLOYMENT_PLAN.md`'s reserved
0015-0020. Supersedes the mechanism in ADR 0019.)*

## Context

ADR 0019 chose outbound email via the business's own Gmail account,
over SMTP on port 587, so a locked-out employee could reset their own
password. That shipped in #188: four routes, a link on the sign-in
page, a three-hour link lifetime, 12 tests.

**It cannot work on the host this project is moving to.** The owner
established (2026-10-29) that DigitalOcean blocks outbound SMTP on
ports 25, 465 and 587 by default on Droplets, Gmail included. Lifting
the block is a discretionary support request, reported in
DigitalOcean's own community threads as granted sometimes and refused
sometimes, so it is not something a deployment plan can depend on.

Verified from this workstation while investigating: TCP connects to
`smtp.gmail.com` on both 587 and 465, TLS completes, `EHLO` returns
`AUTH LOGIN PLAIN`, and the connection is then closed the instant the
`AUTH` command is sent — on a residential line, before any droplet
exists. So SMTP from the application was already untested here and
would have been first exercised in production.

The business is the owner plus a handful of staff. The owner is on
site, knows everybody, and is the person a locked-out employee would
tell first. That is a materially different situation from a service
with strangers for users, and it is the fact that makes the simpler
answer sufficient.

## Alternatives considered

- **A transactional provider on an alternate port** (2525, which exists
  precisely because hosts block the standard ones). Keeps Django's SMTP
  backend and the merged code unchanged — the switch is `.env` values,
  not code. Costs: a vendor account, SPF and DKIM records on a domain
  whose DNS is mid-move, an API credential to rotate, and a free tier
  to keep watching. All to deliver a few password resets a year to
  people the owner can simply speak to.
- **A provider's HTTPS API** (immune to SMTP blocking, since nothing
  blocks 443). Needs either a new dependency or a custom email backend,
  which `CLAUDE.md`'s complexity rule asks us not to add without a
  concrete requirement.
- **Ask DigitalOcean to unblock 587.** Free, and would let ADR 0019
  stand as written. Discretionary, so the recovery path for the whole
  team would rest on a support decision nobody controls. Worth a ticket
  if email is ever genuinely needed; not a foundation.
- **Keep the email flow in place, unused.** Four public routes and a
  sign-in-page link that produce a "check your inbox" page and send
  nothing is worse than having no flow at all: it tells a locked-out
  person to wait for mail that will never arrive.

## Decision

**No email. The owner sets passwords in the app.**

- The Owner-only team member page gains a set-password section, using
  Django's `SetPasswordForm`, so `AUTH_PASSWORD_VALIDATORS` applies
  exactly as it does to a self-service change.
- Setting a password signs that person out everywhere, because the
  session auth hash is derived from the password hash. A compromised
  account is genuinely cut off, not merely given a new key.
- The Owner can create an account, with the role and an initial
  password set at the same moment — there is no invite email, so there
  is nothing to wait for.
- Nobody can set their own password here: the page refuses it and sends
  the owner to the existing self-service change page, the same way the
  access section already refuses.
- The email-based reset flow, its settings, and `CRM_SITE_HOST` are
  removed (unit B). ADR 0019 stays in place as the record of a decision
  the host choice invalidated.

## Reason

It removes a vendor, a credential, two DNS records and a required
startup setting, and replaces them with a page the owner already visits
to set somebody's role and pay. The recovery path becomes "tell the
owner", which is what would have happened anyway in a business this
size — and unlike the email path, it is verifiable in a test rather
than first exercised in production.

## Consequences

- **The owner is the single point of recovery.** If the owner is away,
  a locked-out employee waits. Accepted: the alternative was waiting on
  an email that cannot be sent.
- **The owner briefly knows a password they set**, until the person
  changes it. The owner already has full access to every record in the
  system, so this grants no new reach — but the set-password note tells
  the person to change it, and the self-service change page exists.
- **A password has to be communicated out of band** — spoken, or by
  text. Nothing in the app transmits it.
- **`production.py` no longer requires mail settings**, so a deployment
  cannot fail to start for a missing `EMAIL_HOST`. The development
  console backend stays, so if any future code ever calls `send_mail`
  on a workstation it prints instead of sending.
- **If email is wanted later** — a quote notification from the website,
  say — this ADR does not forbid it. It would need a provider on an
  unblocked port and its own ADR, and password recovery would not have
  to change to accommodate it.

## Date

2026-10-29
