# Moving off RevDek and Wix — the short version

One page. The detail is in `docs/VPS_DEPLOYMENT_PLAN.md`; the evidence
is in `docs/VPS_AUDIT.md`.

## What happens

One $24/month DigitalOcean server runs both the CRM and the new
website. The CRM goes live first, on `crm.heffronexteriorservices.com`,
**without touching the website or the domain** — so if anything is
wrong, nothing customers see is affected. The website follows later,
and Wix is cancelled last.

## The eight phases

| | Phase | Who does the work | Touches the public site? |
|---|---|---|---|
| 1 | Fixes the CRM needs first: email and password reset (done), staff accounts, a limit on login attempts | Me | No |
| 2 | Set up the server | You (I write the guide) | No |
| 3 | **CRM live on `crm.` + backups + a real restore test** | Both | No |
| 4 | Build the website | Me (you supply content) | No |
| 5 | The quote form that feeds leads into the CRM | Me | No |
| 6 | Point the domain at the new server | You, with me watching | **Yes** |
| 7 | Cancel RevDek, then Wix | You | — |
| 8 | Later: online booking, fixing a mistyped payment, two-factor sign-in | Me | — |

Roughly **40-75 hours of my time** and **12-20 hours of yours**, at
whatever pace suits.

## What it costs

| | Now | After |
|---|---|---|
| RevDek | $85/month | — |
| Wix | ? (your invoice) | — |
| Server + backups | — | ~$29-34/month |

**At least $50/month saved**, before whatever Wix costs. The email
stays on your free Gmail account — no new subscription.

## What I need from you

**Decisions:**
1. **Check Wix's DNS settings** — can you add a record for a
   subdomain, and can you edit the main domain's records? This single
   answer decides how the domain move works. It is the only thing
   blocking the full plan.
2. What Wix costs per month, and the domain per year.
3. Do you use **review requests** or a **customer portal** in RevDek?
   They were not on your list but RevDek usually has them.
4. Should a visitor have to give their **full address** to ask for a
   quote, or is a town enough at that stage?

**Content, for the website:** the words, your photos (the original
files, not screenshots), reviews, logo and colours, the service list
and the area you cover. Your Wix site cannot be copied automatically —
it builds its pages with JavaScript — so this has to come from you.

**Accounts you'll need to create:** DigitalOcean (with two-factor and
a spending alert) and Backblaze B2 for off-site backups.

## Where the website lives

In the same repository as the CRM, in a `website/` folder. One place to
deploy from, one backup covering both, and the booking page shares the
site's stylesheet and header rather than carrying a second copy that
drifts.

One rule that matters because **this repository is public**: photos in
that folder are of your own work, published on purpose. A customer's
name or address must never go in there, and nor must screenshots of
the CRM — a photo of a customer's house also carries their location
inside the file unless it is stripped, so a check runs on every change
to catch that.

## Two things worth knowing

**Do not cancel Wix early.** Wix is both your domain registrar and
your DNS host. Cancelling it before the domain is moved would take the
website *and* the CRM offline, and could cost you the domain name.
Your email is unaffected either way — it is on Gmail, not the domain.

**The restore test comes before your real data goes in.** The backup
scripts have never been restored end to end. That is the one thing
that cannot be fixed after the fact, so phase 3 proves it first.

## What you get at the end

The CRM you already have, on your own server, with staff accounts you
can create yourself and a password reset that works; a website you
own; quote requests landing in the CRM as leads instead of an email
you have to retype; nightly encrypted backups off the server, with an
alert if one stops running; and no monthly fee to RevDek or Wix.
