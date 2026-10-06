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
  phone, and address and the work to do (no prices). On a phone your
  bottom bar is Dashboard, Scheduling, Inbox, and Profile.

If your dashboard says **"No role assigned yet"**, or you get a
"permission denied" (403) page, your account doesn't have the role that
page needs — ask the owner. See `docs/PERMISSIONS.md` for the full
model.

On a phone, the app can be installed to your home screen (your
browser's "Add to Home Screen" / "Install app" option) and opens like a
native app.

## Getting around

**The sidebar** on the left lists everything you can open:
**Dashboard**, **Inbox** (team messages; the red number is how many you
haven't read), and groups that open a small menu beside it —
**Customers** (customers, companies, follow-ups, tasks, notes,
activities), **Crew**, **Job** (scheduling, estimates), and **Finance**.
You only see what your role allows. The ☰ button at the top of the
sidebar shrinks it to icons; it stays that way until you click it
again. On a phone or tablet the sidebar opens from the ☰ button in the
top bar instead.

**The top bar** (right side):

- **Search everything…** — click it or press **Ctrl+K** (**⌘K** on a
  Mac) to search customers, companies, jobs (type a number like
  `J-1502`), estimates, and tasks, or to jump straight to any page.
  Use the arrow keys and Enter, or click. Crew members get the jump-to-
  a-page part.
- **Create** — start a new customer, task, or activity log.
- **Refresh**, the **moon** (dark mode on/off — remembered on your
  account, on every device), and the **gear**: your profile, account
  settings, password, the Owner's company settings, and a Dark Mode
  switch.

**Shortcuts:** press **G** then a letter to go somewhere — **G D**
dashboard, **G I** inbox, **G S** scheduling, **G C** customers, **G T**
tasks, **G F** follow-ups, **G E** estimates — or **N C** / **N T** for
a new customer or task. **?** opens the help button's list. (Shortcuts
only include pages your role can open.)

The round **?** button at the bottom right shows these shortcuts and,
if the owner has set one up, an email address for help, ideas, or bug
reports (also in the sidebar).

## Dashboard

The page you land on after logging in. It greets you, says what's on
today, and puts four overview cards at the top. Below them are today's
jobs, **Quick actions** (shortcut tiles to the pages your role may
open), and your tasks and recent activity.

What the cards show depends on your role:

- **Owner** — revenue invoiced this month (with today's and this week's
  on the second line, a small day-by-day chart, and how it compares with
  the same stretch of last month), payments collected, the unpaid
  balance still owed, and jobs completed. Money counts *sent* invoices:
  a draft isn't billed yet, and a voided one was never owed.
- **Sales Rep** — your open estimates and their value, follow-ups due,
  jobs today, and unread messages. No money figures beyond your own
  estimates.
- **Cleaner** — your jobs today, jobs completed and hours logged this
  week, and unread messages.

The Owner also gets two more cards: **Finish setting up** and goals.

### Finish setting up

Until it's done, the Owner sees a short checklist: name your business,
add your logo and contact details, add your first customer, and set a
monthly goal. Each line links to the page that completes it, and ticks
itself off from your actual records — nothing is remembered as a flag,
so if you delete your last customer that line opens again. Once every
line is done the checklist disappears, and **Hide this** removes it
sooner.

### Monthly goals (Owner)

**Settings gear → Monthly goals** sets a target for revenue invoiced,
jobs completed, and new customers. The dashboard then shows how far
through the current calendar month you are against each one. Leave a
field empty to stop tracking it. Goals change nothing about what the
business records — only what the dashboard compares against.

## Notifications

The **bell** in the top bar shows how many unread notifications you
have, and opens the latest few. **See all notifications** lists
everything, newest first; opening one marks it read and takes you to
the record, and **Mark all read** clears the count.

Two things raise a notification today:

- someone assigns you a task (never your own doing — assigning a task
  to yourself notifies nobody);
- a follow-up comes due for a customer you own.

Estimates accepted, jobs finished, and invoices paid join the list as
those workflows arrive in the next phases. Team messages deliberately
don't appear here: the Inbox carries its own unread count.

## Scheduling

**Scheduling** shows jobs by **Day**, **Week** (the default, starting
Monday), or **Month**, colored by service, with arrows and **Today** to
move around. Owners and Sales Reps also see estimate site visits
(dashed, gray) and can pick one crew member to see just their schedule.

Each day carries a row of **dots**, one per booking, colored by service.
A month cell only has room for two jobs, so the dots are how you tell a
quiet day from a full one at a glance; a day with more than six shows
"+3" and the rest. The day view puts the same thing in words above the
list: how many jobs, how many are finished, and how many site visits.

Tap a job for its page: when and where, the customer's phone (tap to
call) and address (tap for directions), the crew and hours, the work,
and notes. Owners and Sales Reps also see prices and the estimate it
came from; the Owner also sees its invoices and whether they're paid.

### Booking a job (Owner and Sales Reps)

**New job** on Scheduling, in the **Create** menu, or on the dashboard.
You pick the customer and, if they have more than one, the address;
when it starts and ends; the service, which sets its color on the
schedule; and who's doing it. Ticking crew members puts the job on
their own schedule.

**The work** is the list of what's being charged for. Picking a service
fills in its usual price, which you can change. You can leave the list
empty while you're only booking the time and price it later.

Opening a job and choosing **Edit** does the same thing again, so that's
also how you move a job to another day or hand it to a different crew.
Hours already logged against a crew member survive the change, and
dropping someone from the crew leaves everyone else's hours alone. A
Cleaner sees their schedule but doesn't set it.

## Estimates

**Estimates** lists what you've quoted and where each one stands, with
filters for status and for your own. **New estimate** writes one: the
customer, the lines of work and their prices, and when you're going to
go and look at it. A booked site visit shows on the schedule.

**Status** is how you move it along. Taking it past Draft records today
as the day it went out, and marking it Accepted records today as the day
it was won; neither date moves if you edit the estimate afterwards, so
a corrected and re-sent estimate keeps the day the customer first saw
it.

Turning an accepted estimate into a booked job is still a manual step —
book the job from Scheduling. The one-click conversion arrives in
Phase 18.

## Business Settings (Owner)

Open the **gear → Business settings**:

- **Company Logo** — choose a JPEG, PNG, GIF, or WebP up to 5 MB. A crop
  box opens: drag the square (or use the arrow keys) and the slider to
  pick what to keep, then **Use this crop** and **Save changes**. The logo
  appears in the sidebar, on the sign-in page, and (later) on estimates
  and invoices. Check **Remove the current logo** to go back to the
  default icon.
- **Business name** — shown everywhere in place of the default name.
  Leave it blank if you work under your own name.
- **Contact Email / Phone** and **website & social links** — what
  customers see. They're separate from your own login and profile.
  One link per platform (Website, Google, Facebook…), plus any number of
  **Other** links, each with a label.
- **Currency** — US or Canadian dollars; every amount in the app follows
  it.
- **Export Data** — download customers, companies, jobs, estimates,
  invoices, payments, expenses, or the team list as CSV (opens in Excel)
  or JSON.

## Reports

**Reports** is a short list of questions worth asking, each answered
over whatever stretch of time you pick: today, this week, this month,
the year so far, or any range you type. Open one and you get a table
with totals, and **Download CSV** gives you the same figures as a file
that opens in Excel.

What's there:

- **Revenue by service** — which work brings the money in.
- **Revenue by sales rep** — who sold what got invoiced.
- **Profit over time** — revenue against expenses, period by period.
- **Expenses by category** — where the money goes.
- **Crew hours and pay** — clocked time and what it cost, per person.
- **Jobs by status** and **Jobs by service** — what you did, how it
  ended up, and how it was rated.
- **New customers** and **Where customers come from** — how many you
  gained and which way of finding you actually works.
- **Estimate outcomes** — how many you win, and who wins them.
- **Follow-ups** — raised against done, by service.

The money reports are yours alone; a Sales Rep sees the rest and is told
how many they're not seeing. Cleaners don't see Reports at all.

Every money figure uses the same definitions as **Profit**, so a report
and that page can't disagree about what a month earned.

## Map

**Map** shows your customers' addresses as pins, with the ones booked
this week in blue, finished jobs in green, and the rest grey. Tap a pin
for the customer, the address, and the next job booked there. The same
list appears below the map, so nothing is reachable only by pointing at
it.

### Placing an address

An address has to be placed before it can be a pin. **Still to place**
lists the ones that aren't, and **Look it up** asks OpenStreetMap where
it is.

**What gets sent, and to whom.** Looking up an address sends *that
address* to the OpenStreetMap Foundation's servers. Never a name, never
a phone number, never anything about the job. Each address is sent once
and the answer is kept, so it isn't sent again unless you edit it.
Viewing the map also asks OpenStreetMap for the map images, which tells
them roughly which area you're looking at.

If an address can't be found, or you'd rather not send it at all, you
can place the pin yourself and nothing leaves this machine.

The map needs internet access. The rest of the app doesn't, and if the
map is unavailable the addresses still list.

## Time clock

**Crew → Time clock** is where you start and stop work. It shows whether
you're on the clock, your hours today, your hours this week, and every
stretch you've clocked since Monday. Everyone with a role has one — the
Owner and Sales Reps do paid work too — and you only ever see your own.

**Clock in** can name the job you're starting, which puts your hours on
it when you clock out, so the job's record and the clock can't tell two
different stories. If you clock onto a job you weren't assigned to, you
are now: you did the work. Leave the job blank for travel, the shop, or
a supply run — that time is still paid, it just isn't charged to a job.

You can only have one clock running. Clocking in twice says so instead
of starting a second one.

## Crew (Owner and Sales Reps)

**Assignments** lays out a week, one card per crew member, with the jobs
they're booked on and the hours logged against each. Jobs nobody is on
are called out at the top, with a link straight to the job so you can
put someone on them. If you've set the days someone normally works, a
job booked outside those days is flagged.

### Payroll (Owner)

**Payroll** is clocked hours times each person's rate, for today, this
week, this month, the year to date, or any range. Someone with no rate
set is still listed with their hours and a warning, because quietly
paying them nothing would be worse than saying so.

Payroll pays for **clocked** time. Hours typed onto a job aren't paid
unless they were clocked.

### Performance (Owner)

**Performance** is how the crew's work looks over a period: jobs
finished, hours clocked, what those jobs were worth in total, what that
works out to per hour, and the average customer rating. Work value is
what the jobs were worth, not what anyone was paid.

### Pay and working days (Owner)

Open someone from **Team** to set their hourly rate and the days they
normally work. Only you can see or set it. The team list shows both at
a glance.

## Invoices, Payments and Expenses (Owner)

The **Finance** menu holds four pages, all Owner-only.

### Invoices

**Invoices** lists what you've billed, with cards for what's billed,
what's been collected, and what's still owed across whatever you're
looking at. The buttons across the top choose which invoices: **Unpaid**
(the default), **Overdue**, **Paid**, **Draft**, **Void**, or **All**.
Paid and overdue aren't something you set — they follow from the
payments and the due date, so a badge can't disagree with the money.

**New invoice** asks which job you're billing; the customer comes from
the job, so the two can never disagree. The quickest way is **Invoice
this job** on a job's own page, which starts the bill from that job's
lines so you don't retype the work. A new invoice is dated today and due
in two weeks, both of which you can change.

**Status** is yours to set: a **Draft** isn't billed yet and isn't
counted as revenue, **Sent** is owed, and **Void** was never owed.

### Payments

On a sent invoice with a balance, **Record a payment** opens a short
form. The amount starts at the balance, so settling a bill in full is
two clicks; change it for a part payment. Paying more than the balance
is allowed — a customer rounds up, or covers two bills with one check —
and the app says so when it happens. **Payments** lists everything
received, newest first, with the total.

### Expenses

**Expenses** is what the work costs you: fuel, supplies, equipment,
payroll, insurance, marketing, or other. Filter by category to see one
kind, with its total. What you record here is what **Profit** subtracts.

## Profit (Owner)

**Profit** shows the money side for **Today**, **This week**,
**This month** (the default), **Year to date**, or any date range up to
five years:

- **Revenue** — what you invoiced (sent invoices, by the date issued;
  drafts aren't billed yet and voided invoices don't count), with the
  number of invoices and the average.
- **Collected** — payments received in the period.
- **Expenses** and **Profit** (revenue minus expenses — a quick owner's
  view, not your accountant's profit and loss).
- **Jobs completed**.
- A chart of revenue and expenses per day, week, or month (tap **Show
  as a table** for the numbers), and revenue split by service and by
  sales rep, and expenses by category.
- **Outstanding today** — what customers still owe, grouped by how late
  it is, and the oldest unpaid invoices (tap one to open its job).

The revenue and outstanding cards on your dashboard open this page.

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

## Messages

**Messages** holds the team channels — **#general** for everyone,
**#crew** for schedules and site notes, and **#sales** for quotes and
leads (Owner and sales reps only) — plus direct messages. The red
number on **Messages** in the menu is how many you haven't read; a
channel you've never opened counts in full until you do. Opening a
channel marks it read.

Type in the box at the bottom and **Send**. To message one person,
open **Message someone** on the Messages page (or **Message** on their
profile). A direct message is private to the two of you — not even the
Owner can read it. New messages appear when you reload the page for
now; automatic updates come in a later update.

## Profile and team

**Profile** shows your details and your numbers for the last 30, 90, or
365 days:

- **Field work** (crew): jobs completed, hours logged and per week,
  average job value, average customer rating, upcoming jobs.
- **Sales** (Owner and sales reps): quotes sent, close rate (won out of
  quotes that were accepted, declined, or expired), value of accepted
  quotes, follow-ups done.

**Edit profile** changes your name, email, title, phone, and your
calendar color. The Owner also sees **Team** — everyone's role, title,
and phone — and can open anyone's profile and stats. Roles themselves
are still set in the admin.

## What's not here yet

Email/calendar integration, file attachments, reporting/forecasting
views, CSV import/export, and an API are not part of this CRM's initial
release — see `docs/ROADMAP.md`'s "Post-release roadmap" for what's
planned next and why each was deferred.
