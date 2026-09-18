# User guide

How to actually use this CRM day to day, once it's deployed and you have
a login. For installing/deploying the application, see
`docs/ADMIN_GUIDE.md`. For how the code is built, see
`docs/DEVELOPER_GUIDE.md`.

## Signing in

Go to the site's root URL and log in with the username/password your
administrator created for you (`python manage.py createsuperuser` for
the first account; every account after that is created via `/admin/` by
a superuser — there is no public sign-up page). After logging in you
land on the **Dashboard**.

If you ever get a "permission denied" (403) page trying to create, edit,
deactivate, or complete something, it means your account hasn't been
added to the **Staff** group yet — ask your administrator. Everyone who
can log in can *see* every record; only Staff members (and superusers)
can change anything. See `docs/PERMISSIONS.md` for the full model.

## Dashboard

The Dashboard (the page you land on after login, and the "Dashboard"
nav link) is a plain at-a-glance summary, refreshed on every page load:

- Active company and contact counts.
- Open lead count (everything not yet marked "Converted").
- Open deal count and total value.
- Your pipeline broken down by stage (Prospecting → Qualification →
  Proposal → Negotiation → Closed won/Closed lost), each with a count
  and total value.
- Your own pending tasks.
- A recent-activity feed across the whole CRM.

There's no charting or configuration here by design — it's server-side
aggregates, not a BI dashboard.

## Search

The search box in the top nav (`?q=...`) searches Companies, Contacts,
Leads, Deals, and Tasks by name/title-like fields at once and shows
matches grouped by type. It does not search Activities (they don't have
their own detail page — see below).

## Companies and Contacts

**Companies** (`Companies` in the nav): list is searchable by name and
filterable by Active/Inactive. A Company's detail page shows its linked
Contacts, Deals, activity timeline, and (if you're Staff) an edit history
section.

**Contacts** (`Contacts`): searchable by first name, last name, or
email; filterable by Active/Inactive and by Company. A Contact's detail
page shows its linked Company, Deals, Tasks, activity timeline, and
history.

Both use **Add** to create, **Edit** to update, and **Deactivate**
instead of delete — deactivating just sets a record inactive (it stops
showing in the default "active" list view but isn't destroyed, so
nothing referencing it breaks). There is no delete button anywhere in
the UI for Companies or Contacts, deliberately.

## Leads

**Leads** (`Leads`) is where new prospects start. A Lead has a status —
New, Contacted, Qualified, Unqualified, or Converted — and you can
search by name, company name, or email, and filter by status.
"Converted" isn't a status you set directly on the edit form; the only
way a Lead becomes Converted is through **Convert**, on the Lead's
detail page:

1. Open the Lead and click **Convert**.
2. Link it to an existing Company, or name a new one to create (not
   both).
3. Fill in the Contact's details (pre-filled from the Lead where
   possible).
4. Optionally check "Also open a deal" and give it a title/value.
5. Submit. This creates/links the Company, always creates a Contact,
   optionally creates a Deal, and marks the Lead Converted.

The original Lead record is kept afterward, not deleted — it's the
historical record of where that Company/Contact/Deal came from. A
Lead can only be converted once; visiting Convert again on an
already-converted Lead just redirects you back to it.

## Deals

**Deals** (`Deals`) tracks your sales pipeline: title, linked Company
and/or Contact (a Deal needs at least one of the two), value, stage,
probability (0–100), and expected close date. List is searchable by
title and filterable by stage or "open only" (excludes Closed won/
Closed lost). Moving a Deal into Closed won or Closed lost from the edit
form sets its closed date automatically.

## Activities

**Activities** (`Activities`) are the call/meeting/email/note log
attached to a Company, Contact, Lead, and/or Deal (an Activity needs at
least one). You'll most often log these from **Add activity** on
whichever record's detail page you're viewing — the form comes
pre-filled with that link. The list view is filterable by type (Call,
Meeting, Email, Note).

Activities have no edit or delete — once logged, they're a permanent
part of that record's timeline (the same "History" section shown on
Company/Contact/Lead/Deal detail pages tracks edits to *those* records,
but Activities themselves are immutable by design).

## Tasks

**Tasks** (`Tasks`) are assignable to-dos, optionally linked to a
Contact and/or Deal, with a due date, priority (Low/Medium/High), and
status (Pending/Completed/Cancelled). Useful list filters:

- `?mine=1` — only tasks assigned to you.
- `?overdue=1` — pending tasks past their due date.
- Status and priority filters, same idea as elsewhere.

Use **Complete** on a task (a one-click action, separate from editing
it) rather than editing its status by hand — it also stamps a
completed-at time. A cancelled task can't be completed by mistake
through this button; the form guards against it.

## What's not here yet

Email/calendar integration, file attachments, reporting/forecasting
views, CSV import/export, and an API are not part of this CRM's initial
release — see `docs/ROADMAP.md`'s "Post-release roadmap" for what's
planned next and why each was deferred.
