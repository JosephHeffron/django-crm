# Database design

This document designed the CRM's initial data model before any code was
written (per `CLAUDE.md`'s "document why before changing architecture" and
"do not overengineer" rules). `apps/crm/models.py` now implements this
design (migrations applied, 38 model tests passing) — see
`logs/claude/phase-02-crm-models.md` for what changed during
implementation (two review-driven additions: a `CheckConstraint` on
`Deal.probability`'s range, and `Activity` locked against admin edits).
A schema review against this document (`docs/DATABASE_REVIEW.md`) is the
next remaining step before Phase 2 is considered fully complete.

All models use `settings.AUTH_USER_MODEL` (Django's built-in `User`) for
ownership/assignment — see "Decisions to review" below for why no custom
user/profile model is introduced here.

## Textual ERD

```
User (django.contrib.auth)
  |
  +---- owns ----> Company, Contact, Lead, Deal   (owner FK)
  +---- assigned ----> Task                        (assigned_to FK)
  +---- authored ----> Activity, Task, Company,     (created_by FK,
        Contact, Lead, Deal                          audit trail)

Company
  |
  +---- Contact       (0..* contacts per company)
  +---- Deal          (0..* deals per company)
  +---- Activity      (0..* activities per company)

Contact
  |
  +---- Activity      (0..* activities per contact)
  +---- Task          (0..* tasks per contact)
  +---- Deal          (0..* deals per contact)

Lead                  (standalone until converted — see Lifecycle)
  |
  +---- Activity      (0..* activities per lead)

Deal
  |
  +---- Activity      (0..* activities per deal)
  +---- Task           (0..* tasks per deal)
```

This mirrors the relationships in `docs/ROADMAP.md` / the original project
brief exactly — no additional relationships (e.g. Task↔Company,
Task↔Lead) have been added. If those turn out to be needed, that's a
decision to make explicitly later, not a default now.

## Entities

### Company

Represents an organization the CRM tracks (a customer, prospect, or
partner org that already has at least one confirmed contact/deal — not a
raw, unqualified lead; see Lead below).

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | CharField(255) | yes | Indexed for search/sort. Not unique — duplicate org names are a real-world data-quality problem to solve later (merge tooling), not a DB constraint. |
| `website` | URLField | no | |
| `phone` | CharField(30) | no | Plain string; no phone-number validation library (avoid overengineering). |
| `industry` | CharField(100) | no | Free text for now, not a foreign-key lookup table — no evidence yet that a controlled vocabulary is needed. |
| `notes` | TextField | no | Free-form. |
| `is_active` | BooleanField | yes, default `True` | Soft "still a live account" flag — companies are never hard-deleted from the UI (see Constraints). |
| `owner` | FK → User | no (nullable) | Current responsible user. `on_delete=PROTECT`. |
| `created_by` | FK → User | yes | Audit trail — who created the record. `on_delete=PROTECT`. |
| `created_at` | DateTimeField | auto | `auto_now_add`. |
| `updated_at` | DateTimeField | auto | `auto_now`. |

Indexes: `name`, `owner`.

### Contact

A person associated with a company (or, occasionally, an independent
individual with no company yet).

| Field | Type | Required | Notes |
|---|---|---|---|
| `first_name` | CharField(100) | yes | |
| `last_name` | CharField(100) | yes | |
| `email` | EmailField | no | Not unique — see Constraints. Indexed. |
| `phone` | CharField(30) | no | |
| `title` | CharField(150) | no | Job title/role at the company. |
| `company` | FK → Company | no (nullable) | `on_delete=SET_NULL` — a contact outlives the company record if one is deleted. Indexed. |
| `notes` | TextField | no | |
| `is_active` | BooleanField | yes, default `True` | |
| `owner` | FK → User | no (nullable) | `on_delete=PROTECT`. |
| `created_by` | FK → User | yes | `on_delete=PROTECT`. |
| `created_at` / `updated_at` | DateTimeField | auto | |

Indexes: `(last_name, first_name)`, `email`, `company`, `owner`.

### Lead

A not-yet-qualified prospect. Deliberately **not** linked to `Company` by
foreign key — a lead is information about a prospective org/person, not a
confirmed one. `company_name` is a plain string until conversion creates
(or matches) a real `Company`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | CharField(200) | yes | Person or company name as given. |
| `company_name` | CharField(255) | no | Free text, not an FK (see above). |
| `email` | EmailField | no | |
| `phone` | CharField(30) | no | |
| `source` | CharField, choices | yes, default `other` | `website`, `referral`, `cold_call`, `event`, `other`. |
| `status` | CharField, choices | yes, default `new` | `new`, `contacted`, `qualified`, `unqualified`, `converted`. See Lifecycle. |
| `notes` | TextField | no | |
| `owner` | FK → User | no (nullable) | `on_delete=PROTECT`. |
| `created_by` | FK → User | yes | `on_delete=PROTECT`. |
| `converted_at` | DateTimeField | no | Set when `status` becomes `converted`. |
| `converted_company` | FK → Company | no (nullable) | Set on conversion, if a Company was created/matched. `on_delete=SET_NULL`. |
| `converted_contact` | FK → Contact | no (nullable) | Set on conversion. `on_delete=SET_NULL`. |
| `converted_deal` | FK → Deal | no (nullable) | Set on conversion, if a Deal was opened. `on_delete=SET_NULL`. |
| `created_at` / `updated_at` | DateTimeField | auto | |

Indexes: `status`, `owner`, `created_at`.

### Deal

An open (or closed) sales opportunity. Tied to a `Company` and/or a
`Contact` — at least one is required (see Constraints), matching the
brief's Company→Deals and Contact→Deals relationships.

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | CharField(255) | yes | e.g. "Acme Corp — annual renewal". |
| `company` | FK → Company | no (nullable) | `on_delete=PROTECT`. Indexed. |
| `contact` | FK → Contact | no (nullable) | `on_delete=PROTECT`. Indexed. |
| `value` | DecimalField(12,2) | no | Single currency assumed (see Decisions to review). |
| `stage` | CharField, choices | yes, default `prospecting` | `prospecting`, `qualification`, `proposal`, `negotiation`, `closed_won`, `closed_lost`. `closed_*` are terminal — "is this deal open" is derived from stage, not a separate field. |
| `probability` | PositiveSmallIntegerField | no | 0-100; manually set, not auto-derived from stage (no evidence yet that auto-derivation is more useful than a human's own estimate). |
| `expected_close_date` | DateField | no | |
| `closed_at` | DateTimeField | no | Set when `stage` transitions to a `closed_*` value. |
| `notes` | TextField | no | |
| `owner` | FK → User | no (nullable) | `on_delete=PROTECT`. |
| `created_by` | FK → User | yes | `on_delete=PROTECT`. |
| `created_at` / `updated_at` | DateTimeField | auto | |

Indexes: `stage`, `owner`, `company`, `contact`, `expected_close_date`.

### Task

A to-do item, optionally tied to a `Contact` and/or `Deal` (matching the
brief's Contact→Tasks and Deal→Tasks relationships — not Company or Lead;
see the ERD note above).

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | CharField(255) | yes | |
| `description` | TextField | no | |
| `assigned_to` | FK → User | yes | `on_delete=PROTECT` — a task must always have an owner; reassign before removing a user. |
| `contact` | FK → Contact | no (nullable) | `on_delete=SET_NULL`. |
| `deal` | FK → Deal | no (nullable) | `on_delete=SET_NULL`. |
| `due_date` | DateField | no | |
| `priority` | CharField, choices | yes, default `medium` | `low`, `medium`, `high`. |
| `status` | CharField, choices | yes, default `pending` | `pending`, `completed`, `cancelled`. |
| `completed_at` | DateTimeField | no | Set when `status` becomes `completed`. |
| `created_by` | FK → User | yes | `on_delete=PROTECT`. |
| `created_at` / `updated_at` | DateTimeField | auto | |

Indexes: `status`, `due_date`, `assigned_to`, `contact`, `deal`.

### AuditLogEntry

A lightweight, append-only record of who changed what on the four "core
business record" models — Company, Contact, Lead, Deal — and when.
Deliberately not a general-purpose event store or a full history/
versioning system (no reconstruction of past states, no revert):
`docs/PROJECT_STATE.md`'s "don't overengineer" rule applies here as much
as anywhere else in this schema.

| Field | Type | Required | Notes |
|---|---|---|---|
| `content_type` | FK → `ContentType` | yes | Which model the change was on. Uses Django's built-in `contenttypes` framework rather than one log table per audited model. |
| `object_id` | PositiveIntegerField | yes | Together with `content_type`, a `GenericForeignKey` to the changed record. Not itself an FK — the referenced record can later be nothing (e.g. hypothetically deleted), same trade-off any generic-relation design accepts. |
| `user` | FK → User | no (nullable) | `on_delete=SET_NULL` — the log entry should survive a user account being removed; `null` covers the (currently theoretical) case of a change with no request-bound user. |
| `action` | CharField, choices | yes | `created` or `updated`. No `deleted` — see Scope below. |
| `changes` | JSONField | yes | `{field_name: [old_display_value, new_display_value]}` for exactly the fields that changed. Empty `{}` for `created` (nothing to diff against). |
| `created_at` | DateTimeField | auto | When the change was recorded. |

Indexes: `(content_type, object_id, created_at)` — the query this table
exists to serve is "show me this record's history, newest first."

**Scope — what is and isn't audited:**

- Only Company, Contact, Lead, Deal are audited. Not Task (lower-stakes,
  and its own status/`completed_at` lifecycle is already visible on the
  record itself) and not Activity (already an immutable append-only log
  by design — auditing an audit trail is redundant).
- Only changes made through the application's own Create/Update views are
  recorded. **Not audited:** Django admin edits, `manage.py shell`/
  management-command changes, and any direct database writes. This is a
  deliberate scope limit, not an oversight — see Decisions below.
- Deactivation (`is_active=False` on Company/Contact) goes through the
  same `UpdateView`-adjacent code path as other field changes and *is*
  captured — it shows up as an `updated` entry with `is_active` in
  `changes`, not as a separate `deleted`-style action, since these
  records are never hard-deleted (see Constraints).
- Lead conversion's side effects (creating a Contact/Company, opening a
  Deal) are recorded as their own `created`/`updated` entries on those
  records through the normal write path — there's no special-cased
  "conversion" audit action.

### Activity

A historical record — call, meeting, email, or note — tied to whichever
of Company/Contact/Lead/Deal it relates to (matching the brief's
Activity relationships on all four). At least one relation is required.
Activities are immutable history: created once, not edited into a
different type or reassigned to a different record.

| Field | Type | Required | Notes |
|---|---|---|---|
| `activity_type` | CharField, choices | yes | `call`, `meeting`, `email`, `note`. "Notes" is this type, not a separate model — see Decisions to review. |
| `subject` | CharField(255) | yes | Short summary line. |
| `description` | TextField | no | Full body/detail. |
| `company` | FK → Company | no (nullable) | `on_delete=SET_NULL` — see below; this was `CASCADE` until `docs/DATABASE_REVIEW.md` finding #2. |
| `contact` | FK → Contact | no (nullable) | `on_delete=SET_NULL`. |
| `lead` | FK → Lead | no (nullable) | `on_delete=SET_NULL`. |
| `deal` | FK → Deal | no (nullable) | `on_delete=SET_NULL`. |
| `created_by` | FK → User | yes | `on_delete=PROTECT`. |
| `created_at` | DateTimeField | auto | Also serves as "when this happened" — no separate `occurred_at` field unless backdating turns out to be a real need. |

Indexes: `activity_type`, `company`, `contact`, `lead`, `deal`,
`created_at`. Composite indexes (e.g. `(company, created_at)` for a fast
"timeline for this company, newest first") are deliberately **not** added
yet — per the Performance Rules in `CLAUDE.md` ("add indexes based on
actual query patterns," "don't optimize speculative problems without
measurements"), these wait until the Activity Timeline feature (Phase 4)
shows the real access pattern.

**Revised during Phase 3** (`docs/DATABASE_REVIEW.md` finding #2): the
original reasoning here was `CASCADE` because "an activity has no
independent meaning once its subject is gone" — true for an Activity
tagged to exactly one record, but the schema always allowed tagging an
Activity to more than one of Company/Contact/Lead/Deal at once, and
`CASCADE` on *any one* of those four FKs destroyed the whole row,
including its relevance to the others that were never deleted.
Confirmed empirically (deleting a Deal wiped out an Activity that was
also tagged to a still-existing Company). Changed all four to
`SET_NULL`: an Activity now survives the deletion of any one of its
tagged records, degrading toward (never past) having zero relations —
consistent with Activity being a historical record, not something that
should vanish because one of several things it once referenced is gone.
No DB constraint stops an Activity being created with zero relations to
begin with, or degrading to zero via `SET_NULL` — see Constraints below.

## Constraints

- **Deal must reference at least one of `company` or `contact`.** Enforced
  with a `CheckConstraint` (`Q(company__isnull=False) | Q(contact__isnull=False)`),
  not just application-level validation, so it holds even for direct DB
  writes. Verified against PostgreSQL: `\d+ crm_deal` confirms the
  constraint is live.
- **Activity has no equivalent DB-level constraint** — it did originally
  (`activity_has_related_object`, "at least one of company/contact/lead/
  deal"), but that's incompatible with `SET_NULL` gracefully degrading
  an Activity to zero relations (the constraint would instead turn that
  degradation into a blocked delete, which was never the intent).
  Removed in the same migration that changed `CASCADE` to `SET_NULL`.
  "At least one relation on creation" is now enforced at the
  application/form layer instead (to be implemented by Activity's
  create view in Phase 4) — a deliberately different level of guarantee
  than Deal's constraint: Deal's rule holds forever, Activity's only
  holds at creation time.
- No uniqueness constraints on `Company.name`, `Contact.email`, or
  `Lead.email` — duplicates are expected and are a data-quality problem for
  a future dedup/merge feature, not something the schema should reject.
- `on_delete=PROTECT` on every `owner`/`created_by`/`assigned_to` FK to
  `User` means a user account can't be deleted while they still own
  records — they must be reassigned first (matches Django's own admin
  deactivation pattern: disable the account, don't delete it).

## Lifecycle behavior

- **Lead conversion**: when a Lead's `status` moves to `converted`, the
  conversion workflow (implemented as application logic, not a DB trigger)
  creates or matches a `Company`/`Contact` and optionally opens a `Deal`,
  then sets `converted_at` and the three `converted_*` FKs on the Lead.
  The Lead row is kept (not deleted) as the historical record of where the
  Company/Contact/Deal came from.
- **Deal closing**: when `stage` transitions to `closed_won` or
  `closed_lost`, `closed_at` is set. "Is this deal still open" is a
  property (`stage not in (closed_won, closed_lost)`), not a stored field,
  so it can never drift out of sync with `stage`.
- **Task completion**: when `status` becomes `completed`, `completed_at`
  is set.

## Decisions that intentionally avoid overengineering

- No custom `Profile`/`Member` model wrapping `User` in this phase — CRM
  models reference `settings.AUTH_USER_MODEL` directly. Role-based
  permissions are planned via Django's built-in Groups/Permissions in the
  later Permissions phase; a custom profile model would only be justified
  if a concrete field (e.g. a phone extension, an avatar) turns out to be
  needed, which nothing today requires.
- "Notes" is an `Activity` type (`activity_type=note`), not a fifth
  top-level model, even though the original feature list mentions
  Activities and Notes as separate bullets — a standalone Note model would
  duplicate the exact same "text + who + when + related to what" shape
  Activity already has.
- No currency field on `Deal.value` — single-currency assumed. Revisit
  only if multi-currency is an actual requirement.
- No industry/source lookup tables (`Company.industry`, `Lead.source`) —
  plain `CharField`/choices instead of a separate model with its own
  admin screen, since nothing yet requires industries or sources to be
  user-manageable data rather than a fixed set of choices in code.
- Composite/query-pattern-driven indexes deferred until the features that
  would actually exercise them exist (see Activity indexes above).
- `AuditLogEntry` rows are written explicitly from each audited model's
  `CreateView`/`UpdateView.form_valid()` — the same place `created_by`
  already gets set and `_sync_deal_closed_at`/`_sync_task_completed_at`
  already run — rather than via `pre_save`/`post_save` signals. Signals
  would catch admin/shell writes too, but they can't see `request.user`
  without a thread-local (a well-known anti-pattern this app has no
  other reason to introduce). Explicit calls from the views that already
  have both the user and the changed fields are simpler and sufficient
  for a single-maintainer app where admin/shell edits are rare and their
  exclusion is accepted (see AuditLogEntry's Scope note above).

## Implementation notes and remaining open questions

This section was written before implementation as "decisions to review";
now that `apps/crm/models.py` exists, each item is marked resolved or
still open.

- **Resolved.** `on_delete=PROTECT` for `owner`/`created_by`/`assigned_to`
  was implemented as designed — a user account can't be deleted while
  they still own records.
- **Resolved.** Deal's multi-column `CheckConstraint` (`deal_has_company_or_contact`)
  was verified against real PostgreSQL (`\d+ crm_deal` after `migrate`) —
  Django's constraint API expresses "at least one of N nullable FKs is
  set" correctly, and a second `CheckConstraint`
  (`deal_probability_between_0_and_100`) was added during implementation
  after review caught that the design's "0-100" note for
  `Deal.probability` wasn't actually enforced. Activity originally had
  an equivalent constraint too, but it was removed in Phase 3 — see the
  `SET_NULL` note under Activity's field table and the Constraints
  section above.
- **Open, still a judgment call to revisit with real usage.**
  `Deal.company`/`Deal.contact` use `PROTECT`, not `SET_NULL`: an earlier
  draft used `SET_NULL`, but since Deal also requires at least one of the
  two to be set (the `CheckConstraint` above), `SET_NULL`-ing a Deal's
  only relation would leave both null and make the delete fail with an
  `IntegrityError` anyway — `PROTECT` makes that failure explicit and
  intentional instead of an accidental side effect of the constraint.
  `Contact.company` has no such constraint (it's a single nullable FK, not
  an "at least one of" pair) so it keeps `SET_NULL`. It may turn out
  users want to delete a Company and have its Deals auto-close instead of
  being blocked — revisit once that's a real request, not before.
- **Revised, no longer an asymmetry.** This originally noted
  `Contact.company` using `SET_NULL` while `Activity`'s four relation
  FKs used `CASCADE`. Both now use `SET_NULL` — Activity's `CASCADE`
  turned out to be a real bug (`docs/DATABASE_REVIEW.md` finding #2,
  fixed in Phase 3), not an intentional asymmetry.
- **Partially resolved.** The lifecycle invariants described above (Lead
  conversion fields set together, Deal/Task timestamps consistent with
  their status) are still enforced only at the application/service
  layer, not by database constraints or triggers — an accepted
  trade-off for a single-maintainer app with no external write path;
  revisit if that stops being true. **Activity immutability is now
  fully resolved**, at two layers: `ActivityAdmin.has_change_permission`
  returns `False` (closes the admin UI path), and `Activity.save()`
  itself now raises `ValueError` on any update to an existing row
  (`docs/DATABASE_REVIEW.md` finding #7 — confirmed empirically that a
  plain `.save()` bypassed the admin-only guard; the model-level guard
  closes that for every write path except bulk `.update()`/
  `.bulk_update()`, which bypass any model's `save()` by design and
  remain a documented, narrower residual gap).
- **Still open.** Whether `Task`/`Activity` should also relate directly
  to `Company` and/or `Lead` (they currently don't, matching the original
  brief's diagram) — revisit if the UI ends up needing a "tasks for this
  company"
  view that the current Contact/Deal-only relations can't answer without
  an extra join.
