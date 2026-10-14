# Permissions

Two layers, both server-side:

1. **Role** decides who may use a page at all (Phase 17,
   `docs/decisions/0008-roles-and-row-level-scoping.md`).
2. **Django model permissions** decide who may change data within an
   allowed page (Phase 6 unit 2) — kept as defense in depth.

History: Phase 6 introduced a single "Staff" group with add/change
permissions and left every other logged-in user as an implicit
*read-only* tier with unrestricted visibility. Phase 17 replaced that
with business roles once the CRM was pivoted to the owner's exterior
home-services company, where crews must not see the customer list or
financials.

## Roles

Roles are Django Groups, created by
`apps/users/migrations/0002_roles.py`. All role logic lives in
`apps/users/roles.py`.

| Role | Who | Can use |
|---|---|---|
| **Owner** | the business owner (any superuser is always Owner) | everything |
| **Sales Rep** | sales staff | dashboard (own quotes and follow-ups, no money figures), calendar, jobs, quotes, contacts, companies, tasks, search (and, as they land: messaging, own profile — not Financials or the service catalog) |
| **Cleaner** | field crew | dashboard (own schedule and hours), calendar and job pages for their own assignments only (no prices), and as they land: messaging, own profile |
| *(no role)* | an account nobody has assigned yet | the dashboard only, which says so — **fail closed** |

Enforcement:

- `RoleRequiredMixin` (and `SalesRoleRequiredMixin` /
  `OwnerRequiredMixin`) — anonymous → login redirect; logged in with the
  wrong role → **403**.
- Row-level scoping (e.g. a cleaner's own jobs) uses queryset helpers;
  an object outside the user's scope returns **404**, so its existence
  isn't revealed (`apps/jobs/access.py`).
- Navigation (`apps/core/navigation.py`) is declared against the same
  role sets as the views, and
  `apps/core/tests/test_navigation.py::NavigationMatchesAccessForEveryRoleTests`
  checks, for every role, that every link shown opens and every page
  not shown is refused — the nav and the views cannot disagree.
- Role membership is managed in the Django admin (a user's Groups), by
  the Owner.

## Permission-to-view mapping

| View | Model action | Permission required |
|---|---|---|
| `CompanyCreateView` | create | `crm.add_company` |
| `CompanyUpdateView` | edit | `crm.change_company` |
| `CompanyDeactivateView` | deactivate | `crm.change_company` |
| `ContactCreateView` | create | `crm.add_contact` |
| `ContactUpdateView` | edit | `crm.change_contact` |
| `ContactDeactivateView` | deactivate | `crm.change_contact` |
| `LeadCreateView` | create | `crm.add_lead` |
| `LeadUpdateView` | edit | `crm.change_lead` |
| `LeadConvertView` | convert | `crm.change_lead` **and** `crm.add_contact` |
| `DealCreateView` | create | `crm.add_deal` |
| `DealUpdateView` | edit | `crm.change_deal` |
| `TaskCreateView` | create | `crm.add_task` |
| `TaskUpdateView` | edit | `crm.change_task` |
| `TaskCompleteView` | complete | `crm.change_task` |
| `ActivityCreateView` | log | `crm.add_activity` |
| `ServiceUpdateView` | edit the service catalog | Owner role **and** `jobs.change_servicetype` |

Notes on the less obvious rows:

- **Deactivation uses `change_<model>`, not a bespoke permission.**
  `CompanyDeactivateView`/`ContactDeactivateView` literally do a
  `.save(update_fields=["is_active"])` — the same primitive
  `change_<model>` already governs everywhere else, and Django doesn't
  auto-create a separate "deactivate" permission. A custom permission
  just for this would be more machinery for a distinction Django's own
  model doesn't draw.
- **`Activity` has no `change_activity` requirement anywhere** — it's
  immutable (no `ActivityUpdateView` exists at all; `Activity.save()`
  itself rejects updates, per `docs/DATABASE_DESIGN.md`), so there's
  nothing to gate beyond `add_activity`.
- **`view_<model>` permissions are never checked** — visibility is
  decided by role (above), not by these auto-created permissions.

## Field-service permissions (Phase 17 unit 2)

`apps/users/migrations/0004_field_service_permissions.py` adds model
permissions for the new models on top of the table above (additive and
reversible). Summary:

| | Owner | Sales Rep | Cleaner |
|---|---|---|---|
| Service catalog | add/change | — | — |
| Quotes + line items | add/change (+ delete lines) | add/change (+ delete lines) | — |
| Jobs, job lines, crew assignments | add/change (+ delete lines/assignments) | add/change (+ delete lines/assignments) | change job, change assignment |
| Photos | add/change/delete | add | add |
| Invoices, payments, expenses | add/change (+ delete lines/expenses) | — | — |
| Properties, tags, notes, business plans, checklist items | add/change/delete | add/change (tags: add) | add note |
| Messages, channel memberships | full | add message; add/change membership | add message; add/change membership |

These say *what kind* of write is possible. *Which rows* a user may
touch is a separate, row-level rule: the scoping helpers in
`apps/jobs/access.py` (a Cleaner sees only jobs they're assigned to and
those customers; only the Owner sees invoices) exist and are tested now,
and every field-service view built on them must use them — read views
in Phase 17 unit 3, write views (e.g. a Cleaner updating only their own
jobs, a user changing only their own channel read marker) in Phases
18-21. Out-of-scope rows return 404, per ADR 0008.
`apps/jobs/tests/test_access.py` and
`test_migrations.py::FieldServicePermissionSeedTests` cover what exists
today.

### A permission can be granted years before the view that honours it

Worth knowing, because it happened and took two phases to notice. The
Cleaner column above has said `add note` since Phase 17, and
`users/0004_field_service_permissions` carries the comment:

> Crews update their own jobs (status, hours) and add photos/notes —
> which jobs is enforced row-by-row in the views.

**No such view existed until Phase 19 unit 3.** A crew member held
`crm.add_note` for two phases and could reach no note interface at all:
the only way in was the Tasks hub, which is sales-and-owner. The
permission was not wrong and the comment was not wrong — the view it
described had simply never been written.

Nothing complains about this. A permission with no view is invisible:
no 403, no error, no failing test. `FieldServicePermissionSeedTests`
asserts the grant exists, which it does, and tells you nothing about
whether anything uses it.

So read this table as **what a role is allowed to do**, not as what
the application offers them. Those are maintained in different places
and nothing keeps them in step.

Measured during Phase 19's close-out. Three different numbers get
confused here, so all three are stated:

| | Count |
|---|---|
| Role-to-permission assignments live on the groups | 106 (Owner 61, Sales Rep 38, Cleaner 7) |
| **Distinct permission codenames** granted to any group | 61 |
| Of those, distinct codenames seeded by `apps/users/migrations/0004_field_service_permissions.py` | 50 |

The breakdown below counts **distinct codenames from that one
migration** — the 50 — because that is the migration this section is
about:

| | Count |
|---|---|
| Enforced by name (`permission_required` or `has_perm`) | 21 |
| Written through a parent form, or by a service function | 20 |
| Reachable by no code path at all | 9 |

The other 11 codenames come from `apps/users/migrations/0002_roles.py`
and `apps/crm/migrations/0005_seed_staff_group.py` — the original CRM
models — and are not analysed here. Four of them (`add_lead`,
`change_lead`, `add_deal`, `change_deal`) are for models **retired in
Phase 18 unit 5**; the stale rows are left deliberately and
`apps/crm/migrations/0011_retire_lead_and_deal.py` says why.

The middle row is **not one category but two**, and the first version
of this section got that wrong by calling it all "parent forms".
Review corrected it; the distinction matters to anyone tracing a write.

**Written through a parent's form or formset.** Quote, job and invoice
line items, and tags on a contact. Django checks no permission for a
formset's own model — the parent view's gate (`jobs.change_quote` and
so on) is the real one, so do not expect to find
`jobs.add_joblineitem` anywhere.

**Written by a service function, with no permission check at all.**
These are not parent-form writes and nothing in the permission system
guards them:

| Write | Where | What actually gates it |
|---|---|---|
| `ChannelMembership` created on first read of a channel | `messaging/services.py` (`mark_read`) | the channel's own audience rule |
| `ChannelMembership` created for a direct message | `messaging/services.py` (`direct_channel`) | both parties being real users |
| `JobAssignment` created by clocking **off** a job you were not assigned to | `jobs/crew.py` (`clock_out` → `_add_hours_to_assignment`) | `jobs_for` scoping on the time-clock view |
| `JobAssignment` created/deleted by editing a job's crew | `jobs/views.py` (`JobFormMixin`) | `jobs.change_job` on the job view |

That is defensible — each has a real gate, just not a permission-shaped
one — but it means the grants for those models are decorative, and a
reviewer looking for the permission that protects a channel membership
will not find one.

The last row is the one to know about:

- `crm.delete_businessplan`, `crm.delete_note`, `crm.delete_property`,
  `messaging.change_message` — the app offers none of these. A plan, a
  note and an address can be created and edited but not removed, and a
  message is immutable.

  The first version of this said "nothing is hard-deleted through the
  UI except photos and checklist items", which review showed was
  wrong. The full inventory of **user-facing hard deletes**:

  | What | How |
  |---|---|
  | A photo | its own remove button (uploader or Owner) |
  | A checklist step | its own remove button |
  | A quote, job or invoice **line item** | the **Remove** checkbox on the edit form (`can_delete=True`, rendered by `jobs/_line_row.html`) |
  | A **crew assignment** | taking someone off a job in the job edit form (`JobFormMixin` deletes the row) |

  The last two are easy to miss because they look like edits rather
  than deletions — you untick a box or deselect a name — and that is
  exactly why they belong in this list. Note the crew-assignment delete
  is deliberately *not* a replace-all: `JobFormMixin` adds and removes
  individually so hours already logged against someone survive an
  unrelated edit.
- `jobs.change_photo`, `jobs.delete_photo` — removal *is* offered, but
  `PhotoDeleteView` gates it on "whoever uploaded it, or the Owner"
  rather than on the permission (Phase 18 unit 2's decision). The grant
  is decorative; the ownership rule is the real one.
- `jobs.change_payment`, `jobs.delete_expense` — a payment can be
  recorded but not corrected, and an expense edited but not removed.
- **`jobs.add_servicetype`** — the Owner is granted it and **there is
  no create route**: `ServiceListView` and `ServiceUpdateView` exist,
  nothing adds a service. A business that starts offering a new service
  must use the Django admin. Noted in `docs/PROJECT_STATE.md`'s known
  issues.

To check a row yourself: find the permission in
`apps/users/migrations/0004_field_service_permissions.py`, then grep
for both
`permission_required = "<app>.<codename>"` and
`has_perm("<app>.<codename>")`. A grant matching neither is either
written through a parent form or a promise nothing keeps — and the two
look identical from here, which is why the list above is spelled out
rather than left as a method.

## Field-service pages (Phase 17 unit 3)

Messages: a public channel's `audience` decides who may read and post
(everyone, or the Owner and sales reps); a direct channel is readable
only by its two members — the Owner included. Every list, count, and
page goes through `apps/messaging/services.visible_channels()`, so the
unread badge, the channel list, a contact's timeline, and the channel
URL agree. Posting also requires `messaging.add_message`. Editing your
own profile needs only a role (self-service, like changing your
password).

A contact's timeline includes team messages that mention them only from
channels the viewer can read (public channels and ones they're a
member of), so a direct message never leaks onto a contact page.

| Page | Owner | Sales Rep | Cleaner |
|---|---|---|---|
| Dashboard (`/`) | whole business, with revenue and outstanding balance | own open quotes, follow-ups, site visits; no money figures | own jobs today and coming up, own hours |
| Calendar (`/calendar/`) | all jobs + site visits, crew filter | all jobs + site visits, crew filter | own assigned jobs only (crew filter ignored) |
| Job (`/jobs/<id>/`) | yes, with prices and invoices | yes, with prices | only if assigned (else 404); customer name, phone, address, work — no prices |
| Quote (`/quotes/<id>/`) | yes | yes | 403 |
| Financials (`/financials/`) | yes | 403 | 403 |
| Messages (`/messages/`) | #general, #crew, #sales, own DMs | #general, #crew, #sales, own DMs | #general, #crew, own DMs (#sales → 404) |
| Profile (`/profile/`, edit) | own | own | own |
| Team (`/team/`, a teammate's profile) | yes | 403 | 403 |
| Services (`/settings/services/`) | view and edit | 403 | 403 |
| Business Settings (`/settings/business/`) and data export | yes | 403 | 403 |
| Monthly goals (`/settings/goals/`) | view and edit | 403 | 403 |
| Book or change a job (`/jobs/new/`, `/jobs/<pk>/edit/`) | yes | yes | 403 |
| Write or change an estimate (`/quotes/new/`, `/quotes/<pk>/edit/`) | yes | yes | 403 |
| Invoices (`/invoices/`, create, edit) | yes | 403 | 403 |
| Record a payment (`/invoices/<pk>/payments/new/`), Payments | yes | 403 | 403 |
| Expenses (`/expenses/`, create, edit) | yes | 403 | 403 |
| Time clock (`/time-clock/`) | own | own | own |
| Map (`/map/`) | yes | yes | 403 |
| A job photo (`/photos/<uuid>/`) | any | any | only on their own jobs |
| A teammate's picture (`/people/<username>/photo/`) | yes | yes | yes |
| Reports (`/reports/`) | every report | all but the money ones | 403 |
| Settings hub (`/settings/`) | yes | yes | yes |
| What's new (`/whats-new/`) | yes | yes | yes |
| Customize (`/settings/customize/`) | yes | 403 | 403 |
| Activity log and undo (`/settings/activity/`) | yes | 403 | 403 |
| Set someone's role or sign-in (`/team/<username>/`) | yes | 403 | 403 |
| A money report (`/reports/revenue-by-service/` and so on) | yes | 404 | 403 |
| Place an address (`/map/properties/<pk>/locate/`) | yes | yes | 403 |
| Assignments (`/crew/assignments/`) | yes | yes | 403 |
| Payroll (`/crew/payroll/`) | yes | 403 | 403 |
| Performance (`/crew/performance/`) | yes | 403 | 403 |
| Set someone's pay rate and working days (`/team/<username>/`) | yes | 403 | 403 |
| Setup checklist (dashboard, `/onboarding/dismiss/`) | yes | not shown | not shown |
| Notifications (`/notifications/`) | own | own | own |
| Contacts (`/contacts/`, a contact's page) | yes | yes | 403 |
| Tasks hub (`/tasks/`: tasks, follow-ups, quotes, plans, notes) | yes | yes | 403 |

Leads and Deals are gone. Phase 17 folded them into Contacts and
Quotes (ADR 0009) and Phase 18 unit 5 removed the models and their
pages. `/leads/` and `/deals/` now redirect permanently to Customers
and Estimates, since both were in the menu for most of this project's
life; the pages they redirect to enforce their own access, so the
redirects grant nothing. Their detail and add URLs 404 — there is no
record to point at. `LeadConvertView`, which used to be the one view in
the app requiring two permissions at once, went with them.

## Seeding the role groups

`apps/users/migrations/0002_roles.py` creates `Owner`, `Sales Rep`, and
`Cleaner`. Owner and Sales Rep get exactly the 11 permissions in the
table above (the set the Phase 6 "Staff" group held, originally seeded
by `apps/crm/migrations/0005_seed_staff_group.py`); Cleaner gets none.
Existing Staff members become Sales Reps and the Staff group is
removed. The migration is reversible — its reverse restores Staff with
its permissions and members. Both directions are exercised in
`apps/crm/tests/test_permissions.py::RolesMigrationTests`.

A migration (not a manual admin step) because this needs to exist
identically in every environment, the same way the schema does.

**A real Django migration-ordering gotcha, handled explicitly**:
model permissions (`add_company`, etc.) are normally created by a
`post_migrate` signal that fires once, after *every* migration in a
`migrate` run has already applied — including this one. On a genuinely
fresh install, querying `Permission.objects.get(codename="add_company")`
*inside* this migration would run before that signal has ever fired,
and fail. The migration calls
`django.contrib.auth.management.create_permissions` itself, for every
installed app, before looking anything up — the same pattern Django's
own documentation and ecosystem use for exactly this "seed a group in
a migration" scenario. Verified by actually running this migration
against a completely fresh database (not just a database that had
already been migrated normally once before), not assumed to work from
reading about the pattern.

## The 403 page

Django's default `PermissionDenied` handling shows a plain "Forbidden"
page unless a custom `403.html` exists — the same DEBUG-gated
mechanism as the existing custom `404.html` (Phase 3): only rendered
when `DEBUG=False`, exercised in tests the same way
(`@override_settings(DEBUG=False, ...)`), not via the dev server where
Django's own debug page takes over. Added `templates/403.html`
matching `404.html`'s existing style, rather than leaving Django's bare
default.

## What this doesn't do (deferred, not forgotten)

- No custom "assign a role" UI — group membership is managed through
  the Django admin, which already does this.
- No per-model permission distinctions beyond the table above (e.g. no
  "Task-only" role) — nothing asks for that granularity.
- `view_<model>` permissions remain unused: visibility is decided by
  role and row-level scoping instead.
