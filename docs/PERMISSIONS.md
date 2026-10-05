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
- **`LeadConvertView` needs two permissions, not one.** The view is
  one atomic business operation (link/create a Company, always create
  a Contact, optionally open a Deal, then mark the Lead converted) but
  spans several models. Requiring `change_lead` alone would let
  someone convert a lead without being allowed to create Contacts
  anywhere else in the app — an odd asymmetry. Company/Deal creation,
  which only happen conditionally inside the same view, are treated as
  an accepted side effect of an already-authorized conversion, not
  separately gated — adding `add_company`/`add_deal` checks for a
  sometimes-nil code path would be more complexity than the actual
  risk here justifies.
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
| Assignments (`/crew/assignments/`) | yes | yes | 403 |
| Payroll (`/crew/payroll/`) | yes | 403 | 403 |
| Performance (`/crew/performance/`) | yes | 403 | 403 |
| Set someone's pay rate and working days (`/team/<username>/`) | yes | 403 | 403 |
| Setup checklist (dashboard, `/onboarding/dismiss/`) | yes | not shown | not shown |
| Notifications (`/notifications/`) | own | own | own |
| Contacts (`/contacts/`, a contact's page) | yes | yes | 403 |
| Tasks hub (`/tasks/`: tasks, follow-ups, quotes, plans, notes) | yes | yes | 403 |

Leads and Deals are no longer in the menu (folded into Contacts and
Quotes, ADR 0009); their old pages stay reachable by URL, with the same
Owner/Sales Rep access, until Phase 18 removes them.

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
