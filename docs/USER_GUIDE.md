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

What you can see depends on your **role**, which the owner assigns:

- **Owner** — everything.
- **Sales Rep** — the calendar, jobs, quotes, customers (contacts,
  companies), tasks, and search. No revenue figures.
- **Cleaner** — your own schedule: the dashboard and calendar show only
  the jobs you're assigned to, and a job page shows the customer's name,
  phone, and address and the work to do (no prices).

If your dashboard says **"No role assigned yet"**, or you get a
"permission denied" (403) page, your account doesn't have the role that
page needs — ask the owner. See `docs/PERMISSIONS.md` for the full
model.

On a phone, the app can be installed to your home screen (your
browser's "Add to Home Screen" / "Install app" option) and opens like a
native app.

## Dashboard

The page you land on after logging in. It's different for each role:

- **Owner** — revenue invoiced today and this week (sent invoices; a
  draft isn't billed yet), the unpaid balance still owed, open quotes,
  follow-ups due, unread team messages, today's schedule, site visits in
  the next seven days, your tasks, and recent activity.
- **Sales Rep** — the same minus the money figures, with quotes,
  follow-ups, and site visits limited to your own.
- **Cleaner** — your jobs today and coming up, jobs completed and hours
  logged this week, and unread messages.

## Calendar and jobs

**Calendar** shows jobs by **Day**, **Week** (the default, starting
Monday), or **Month**, colored by service, with **Prev** / **Today** /
**Next** to move around. Owners and Sales Reps also see quote site
visits (dashed, gray) and can pick one crew member to see just their
schedule. On a phone the month view shows how many jobs each day has —
tap a date for the day's details.

Tap a job for its page: when and where, the customer's phone (tap to
call) and address (tap for directions), the crew and hours, the work,
and notes. Owners and Sales Reps also see prices and the quote it came
from; the Owner also sees its invoices and whether they're paid.

A **quote** page (from the calendar or dashboard) shows its status,
line items and total, the site visit, and any jobs booked from it.
Creating and editing quotes and jobs arrives in Phase 18.

## Services (Owner)

**Services** in the menu is the price list: each service's default
price and unit, how many months after a job the customer gets a
follow-up (blank = never), its calendar color, and whether you still
offer it. Changing a price only affects new quotes — existing quotes,
jobs, and invoices keep the prices they were written with.

## Search

The search box in the top nav (`?q=...`) searches Companies, Contacts
(name, email, or phone), Leads, Deals, and Tasks at once and shows
matches grouped by type. Type a job or quote number — `J-1502`,
`q1067` — to jump straight to it. It does not search Activities (they don't have
their own detail page — see below).

## Companies and Contacts

**Companies** (`Companies` in the nav): list is searchable by name and
filterable by Active/Inactive. A Company's detail page shows its linked
Contacts, Deals, activity timeline, and an edit history section.

**Contacts** (`Contacts`): your customers and leads. Tabs switch
between All, Leads, and Customers; search by name, email, or phone; and
filter by tag, company, or active/inactive. The list shows each
contact's last completed job and last contact, and can be sorted by
**Longest since contact** — the people most overdue for a call come
first. On a phone each contact is a card.

A contact's page shows their phone (tap to call), email, preferred way
to be reached, where they came from, properties (tap an address for
directions), upcoming jobs, tasks, and a **Timeline** of everything
that's happened — jobs, quotes, notes, logged calls and texts, and team
messages that mention them (a direct message only shows to the people
in that conversation). **Edit** sets whether they're a lead or a
customer, the lead source, and tags. Adding and changing service
addresses arrives with the quote builder in Phase 18.

Both use **Add** to create, **Edit** to update, and **Deactivate**
instead of delete — deactivating just sets a record inactive (it stops
showing in the default "active" list view but isn't destroyed, so
nothing referencing it breaks). There is no delete button anywhere in
the UI for Companies or Contacts, deliberately.

## Leads

*Leads and Deals have moved:* every lead is now a Contact with the
status "Lead", and every deal is a Quote. They're no longer in the
menu; the old pages below still open by URL until Phase 18 removes them.

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

**Tasks** is a hub with five tabs:

- **Tasks** — assignable to-dos (below).
- **Follow-ups** — customers due for repeat service: nobody has done
  that service or been in touch within its interval (set per service on
  the Services page). Each shows who to call and their number; **Mark
  done** logs the check-in, which restarts that customer's clock.
  **Done** and **Dismissed** show past ones; **Only mine** narrows to
  yours. The tab's badge counts follow-ups due today or earlier.
- **Quotes** — open quotes (draft or sent) by default, or filter by
  status; **Only mine** shows quotes you prepared.
- **Plans** — business goals with checklist progress. Editing plans
  and ticking off steps arrives in Phase 19.
- **Notes** — team notes, pinned first; filter to general notes or
  ones about a customer or a job, or search them.

Tasks themselves are assignable to-dos, optionally linked to a
Contact, with a due date, priority (Low/Medium/High), and status
(Pending/Completed/Cancelled). Useful list filters:

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
