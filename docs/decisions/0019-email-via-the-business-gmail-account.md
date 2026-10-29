# 0019 — Outbound email via the business's own Gmail account

*(Numbered per `docs/VPS_DEPLOYMENT_PLAN.md`'s ADR table rather than
creation order, so the plan's references stay true. 0015-0018 and 0020
arrive with their own units.)*

## Context

The app has never sent an email. There is no `EMAIL_BACKEND`,
`EMAIL_HOST` or `DEFAULT_FROM_EMAIL` anywhere in `config/settings/`
(`docs/VPS_AUDIT.md` F-CRM-3), so Django would fall back to trying
localhost:25 and fail.

That blocks the thing that actually matters: **a locked-out employee
cannot get back in.** `apps/users/urls.py` offers login, logout and
password-*change* — the last of which requires already being signed
in. Recovering a forgotten password needs the owner to open the Django
admin, which is not a workable answer for a business with staff.

What the app needs to send is small and will stay small: password
resets for a handful of people, and later one notification when
somebody asks for a quote through the website. Not newsletters, not
customer campaigns, not anything with a schedule.

The business email (owner, 2026-10-27) is a **free Gmail account**,
`heffronexteriorservices@gmail.com`. The domain itself has **no MX,
SPF, DKIM or DMARC records at all** (`docs/VPS_AUDIT.md` §8, verified
by lookup), so no mail is deliverable to the domain today and none is
sent from it.

## Alternatives considered

- **A transactional provider** (Postmark, Resend, SES, Mailgun). Better
  deliverability reporting, bounce handling, webhooks, and an API key
  scoped to sending rather than a credential for a whole mailbox. All
  of which matter at volume, and none of which is needed to send three
  password resets a year. It also wants DNS records — SPF and DKIM on
  a domain whose DNS is still hosted at Wix and about to be moved
  (plan §7), so adopting one now means doing that work twice.
- **Mail on the domain** (`info@heffronexteriorservices.com`, via
  Google Workspace or a cheaper mailbox host). A better From address,
  and a real cost per user per month. It is a separate decision from
  *how the app sends*, and nothing about launching needs it.
- **No email; the owner sets passwords by hand.** Honest, and it is
  what happens today. Rejected because it makes the owner a single
  point of failure for something that happens at the worst possible
  moment, and because the website form in a later phase needs to
  notify somebody.
- **Sending nothing to customers, ever.** Kept, in part — see the
  decision: at launch the app notifies *staff* only.

## Decision

**Send through the existing Gmail account over SMTP, with an app
password, and notify only people inside the business.**

- `config/settings/production.py` configures SMTP from the
  environment. `EMAIL_HOST`, `EMAIL_HOST_USER` and
  `EMAIL_HOST_PASSWORD` are **required** — read with `os.environ[...]`
  like `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS` — so a
  half-configured deployment fails at startup instead of silently
  failing to send a reset link weeks later. Port and TLS have defaults
  (587, on).
- `config/settings/development.py` uses the **console backend**. Mail
  written on a workstation is printed, never sent: no credential is
  needed to develop, and no test or seed run can email a real person.
- `DEFAULT_FROM_EMAIL` falls back to `EMAIL_HOST_USER`, because Gmail
  will not send as an address the account does not own.
- **No DNS records are needed.** Mail leaves through Google's own
  servers as a `gmail.com` address, which Google already signs. This
  is the main practical reason for the choice: it keeps SPF and DKIM
  out of a DNS cutover that has enough moving parts already.
- **`CRM_SITE_HOST`** (optional) fixes the hostname used in links
  inside emails. See Consequences — this exists to prevent a specific
  breakage in a later phase, not for tidiness.

## Reason

The volume is tiny, the credential already exists, it costs nothing,
and it needs no DNS. Every argument for a transactional provider is an
argument about scale or about customer-facing mail, and this app is
about to send neither. When that changes — the first customer-facing
confirmation email — the decision gets revisited with a real need
behind it, which is the opposite of adopting a dependency now in case.

## Consequences

- **The From address is `@gmail.com`.** Fine for staff; it is one
  reason customer-facing mail is deliberately out of scope here.
- **No delivery visibility.** If Google defers or drops a message,
  nothing in the app knows. Acceptable for resets to colleagues, and
  the thing a provider would buy us.
- **An app password is a long-lived credential** in `.env` with
  authority to send as the business. It is the same `.env` that holds
  the database password and the restic key, so the handling is already
  established: never committed, inside the encrypted backup. It
  requires 2-Step Verification on the Google account, and **Google has
  been narrowing app-password access** — if it is withdrawn, this ADR
  is what gets revisited, and the replacement is a provider.
- **Gmail's limits** (in the region of a few hundred recipients a day
  for a free account) are far above this app's needs and far below a
  campaign tool's. If anything in this app ever wants to mail every
  customer at once, that is the signal to stop and reconsider, not to
  raise a limit.
- **Email links must not point at the website's hostname.** Django
  builds reset links from the request's host. Once the apex and `www`
  join `ALLOWED_HOSTS` for the public booking form (plan D1), a reset
  requested through that origin would email a link to
  `heffronexteriorservices.com/accounts/...`, which Caddy does not
  proxy to Django — a dead link in the one email that has to work.
  `CRM_SITE_HOST`, when set, pins the domain in email links to the CRM
  host regardless of which host the request arrived on. A test holds
  it.
- **The browser-pass harness and anything else importing production
  settings now need the three email variables set**, because they are
  required. That is the intended cost of failing fast.

## Date

2026-10-27
