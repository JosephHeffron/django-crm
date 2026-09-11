# Database review

A senior-reviewer pass on the implemented schema (`apps/crm/models.py`,
migrations `0001_initial` and `0002_deal_deal_probability_between_0_and_100`)
against `docs/DATABASE_DESIGN.md`. This is a review only — nothing in the
schema was changed to produce it. Findings that turned out to need
verification were checked against the real local PostgreSQL database
(`\d+`, `pg_constraint`, and live delete experiments), not just read from
the model code.

Severity: **HIGH** (real risk of silent/surprising data loss or
inconsistency) / **MEDIUM** (a real gap worth a deliberate decision) /
**LOW** (worth knowing, not urgent) / **INFO** (confirms the design is
sound as implemented).

## HIGH

### 1. `on_delete` behavior is enforced by Django's ORM, not by PostgreSQL

Checked directly against `pg_constraint`:

```sql
SELECT conrelid::regclass, conname, confdeltype
FROM pg_constraint WHERE contype = 'f';
```

Every foreign key in the schema — all 32 of them, across every model,
regardless of whether Django declares `PROTECT`, `SET_NULL`, or
`CASCADE` — has `confdeltype = 'a'` (`NO ACTION`) at the actual database
level. Django implements `on_delete` entirely in Python (the ORM's
deletion `Collector`), not as native `ON DELETE CASCADE`/`SET NULL`
clauses.

Confirmed empirically, not just inferred: created a `Company` with an
`Activity` attached, then ran `DELETE FROM crm_company WHERE id = 1;`
directly in `dbshell`:

```
ERROR:  update or delete on table "crm_company" violates foreign key
constraint "crm_activity_company_id_e2847e3b_fk_crm_company_id" on
table "crm_activity"
DETAIL:  Key (id)=(1) is still referenced from table "crm_activity".
```

The documented "Activity is CASCADE-deleted with its Company" behavior
did **not** happen — the raw delete was blocked instead, for reasons
that have nothing to do with the declared `on_delete=CASCADE`. Deleting
the same `Company` via `Company.objects.get(...).delete()` (going
through the ORM) correctly cascaded.

**Impact**: any deletion path that doesn't go through Django's ORM —
`psql`, a future raw-SQL data migration, a one-off DBA cleanup, a bulk
import/export tool — will not honor `CASCADE`/`SET_NULL`/`PROTECT` as
documented. `PROTECT` "accidentally" still works (the delete is blocked
either way), but `CASCADE` and `SET_NULL` do not — a raw delete that's
supposed to cascade will instead fail outright with a constraint
violation, which is a different (if arguably safer) failure mode than
what's documented.

This is standard Django behavior, not a defect introduced by this
schema, but it isn't currently mentioned anywhere in
`docs/DATABASE_DESIGN.md` or `CLAUDE.md`'s Database Safety policy, and
this project explicitly calls out "ad-hoc SQL" as a real risk category
("Never modify production data through ad-hoc SQL"). Recommend adding a
line to `CLAUDE.md`'s Database Safety section stating this explicitly:
`on_delete` guarantees only hold for deletions performed through Django.

**Status: RESOLVED.** Added the recommended line to `CLAUDE.md`'s
Database Safety section. This is inherent Django behavior, not
something the schema itself can fix — the resolution is making sure
anyone (human or AI) operating on this database knows it, not a code
change.

### 2. Activity's four-way `CASCADE` can destroy history that's still relevant to a surviving object

`Activity.company`/`contact`/`lead`/`deal` all use `CASCADE`, and the
schema permits (doesn't forbid) tagging an Activity to more than one of
them at once — the `activity_has_related_object` constraint is an `OR`,
not an `XOR`.

Confirmed empirically: created a `Company`, a `Deal` on that `Company`,
and an `Activity` tagged to **both** the `Company` and the `Deal`. Then
deleted only the `Deal` (not the `Company`) through the ORM:

```
Before delete — company exists: True
Before delete — activity exists: True
After deleting the Deal (not the Company):
  company still exists: True
  activity still exists: False
```

The Activity — a call log entry that was also part of the Company's own
activity timeline — was silently destroyed as a side effect of deleting
an unrelated Deal, even though the Company it was equally attached to
was never touched. `docs/DATABASE_DESIGN.md`'s stated rationale for
`CASCADE` ("an activity has no independent meaning once its subject is
gone") assumed a single subject; it doesn't hold once an Activity can
have multiple subjects, which the schema currently allows.

**Recommendation** (not applied — this is a review, not a fix):
either (a) restrict an Activity to exactly one relation (a `CheckConstraint`
requiring exactly one of the four FKs, not "at least one"), which would
make the current `CASCADE` reasoning correct again, or (b) keep multi-tagging
allowed and switch to `SET_NULL` for these four FKs instead of `CASCADE` —
note this option is not a drop-in change: the existing
`activity_has_related_object` constraint requires at least one relation
be non-null, so `SET_NULL`-ing an Activity's last remaining relation
would violate that constraint and block the deletion instead of
producing an orphaned Activity. Making (b) work requires also relaxing
or removing that constraint, or adding explicit cleanup behavior for
Activities that would otherwise end up fully orphaned. Worth
resolving explicitly before the Activity Timeline feature (Phase 4) starts
relying on this data staying intact.

**Status: RESOLVED — chose option (b).** Changed all four relation FKs
to `SET_NULL` and removed the `activity_has_related_object`
`CheckConstraint` (a migration doing both). Chose (b) over (a) because
multi-tagging is real product value for a future Activity Timeline (the
same call showing up on both a Company's and a Deal's timeline is a
feature, not a bug) — restricting to exactly one relation would trade
away that value to avoid a problem `SET_NULL` solves directly.
"At least one relation required" moved from a DB constraint to an
application/form-layer rule for Activity *creation* only (to be
implemented by Activity's create view in Phase 4) — an Activity can
still degrade to zero relations over time as things it references get
deleted, which is the intended behavior, not a gap. Re-verified
empirically: the exact scenario above (Activity tagged to both a
Company and a Deal, Deal deleted) now leaves the Activity intact with
`deal` set to `None` and `company` unchanged. See
`docs/DATABASE_DESIGN.md`'s Activity section and
`apps/crm/tests/test_activity.py` for the updated model and tests.

## MEDIUM

### 3. `Deal.company` and `Deal.contact.company` can silently disagree

When both `Deal.company` and `Deal.contact` are set, nothing — not a
`CheckConstraint`, not application validation — requires
`Deal.company == Deal.contact.company`. A Deal can end up pointing at
one Company directly while its linked Contact belongs to a different
Company, with no error and no obvious way to notice. Worth deciding
whether this needs enforcement (a `CheckConstraint` comparing the two
isn't directly expressible in a single-table check since it requires a
join — this would need either a trigger or application-layer validation
in a future `Deal.clean()`) or is an accepted possibility (e.g. a
Contact who changes employer mid-deal, and the Deal intentionally keeps
its original Company).

### 4. `TextChoices` fields are validated by Django, not by PostgreSQL

Confirmed precisely, not assumed: `Activity(activity_type="bogus", ...).full_clean()`
correctly raises `ValidationError`, but `Activity.objects.create(activity_type="bogus", ...)`
succeeds and writes `"bogus"` straight into the database (this is
exercised by
`test_activity_type_choices_are_enforced_in_forms_not_the_db`). The
database only enforces `max_length`; the choice restriction is enforced
by `full_clean()` (which `ModelForm`/admin call, but plain `.save()`/`.create()`
do not call automatically).

This applies to all six choice-backed fields across the schema
(`Lead.source`, `Lead.status`, `Deal.stage`, `Task.priority`,
`Task.status`, `Activity.activity_type`) — not just `Activity`, which is
the only one currently exercised by a test. `docs/DATABASE_DESIGN.md`
already documents this trade-off for the Activity-immutability case, but
frames it there as specific to Activity; it's actually a schema-wide
characteristic worth naming as such. A `CheckConstraint` with
`field__in=[...]` per choice field is possible if DB-level strictness is
ever wanted, at the cost of a migration every time a choice is added
(vs. the current zero-migration cost of adding a `TextChoices` member).

### 5. `Company` has no address fields

Not present in either `docs/DATABASE_DESIGN.md` or the implementation.
For a CRM, a company's mailing/billing address is fairly standard data
(regional filtering, mail campaigns, invoicing later). This may well be
a deliberate MVP scope cut rather than an oversight, but it wasn't
explicitly called out as "deferred" the way currency or lookup tables
were — worth a conscious yes/no rather than silence.

### 6. `Deal.company`/`Deal.contact` `PROTECT` means a Company/Contact can never be hard-deleted once it has any deal history

Even a single `closed_lost` deal from years ago permanently blocks
deleting the Company or Contact it references. This is very likely the
intended trade-off (`Company.is_active`/`Contact.is_active` are the
actual "remove from view" mechanism, not hard delete) — but
`docs/DATABASE_DESIGN.md` doesn't state this consequence explicitly, and
it's the kind of thing worth being deliberate about before it's
discovered as a support request ("why can't I delete this company?").

### 7. Activity immutability is enforced only in the admin, not at the model layer

`docs/DATABASE_DESIGN.md` documents Activity as immutable history, and
PR #11 closed the one mutation path that existed at the time
(`ActivityAdmin.has_change_permission` returning `False`). Confirmed
empirically that this doesn't actually make Activity immutable —
`activity.subject = "edited"; activity.save()` from a plain Django shell
succeeds without error, silently rewriting supposedly-immutable history:

```
subject after edit: Edited after creation via plain .save()
```

The admin restriction only blocks the Django admin UI specifically; any
other code path (a future custom view, a management command, `./manage.py
shell`, a data-migration script) can still edit or reassign an existing
Activity's type, subject, description, or related-object FKs with no
guard at all. `docs/DATABASE_DESIGN.md` already frames the broader
enforcement gap as an accepted application-layer trade-off — this finding
confirms that trade-off is real and currently as wide-open as before
PR #11's admin fix, for every write path except the admin itself.

**Status: RESOLVED.** `Activity.save()` now raises `ValueError` when
called on an instance that already has a `pk` — closes the gap for
every write path that goes through `.save()` (shell, future views,
management commands, this included). Re-verified the exact reproduction
above: `activity.subject = "Edited"; activity.save()` now raises
instead of succeeding, and the DB value is unchanged after. Confirmed
this doesn't interfere with the `SET_NULL` fix for finding #2 — Django's
deletion `Collector` performs `SET_NULL` via a bulk `QuerySet.update()`
call, not by calling each affected instance's `.save()`, so the two
changes don't conflict. Residual, documented gap: `.update()`/
`.bulk_update()` calls still bypass `save()` entirely, same as any
Django model — not fixed, since blocking those would need overriding
`QuerySet`/`Manager` behavior project-wide, disproportionate to the
actual risk for a single-maintainer app with no bulk-write code today.

## LOW

- **No "primary contact" flag.** A Company with several Contacts has no
  way to mark which one is the main point of contact. Common CRM
  feature, reasonable to defer to a later phase.
- **Inconsistent lifecycle-flag shape across models.** `Company`/`Contact`
  use a boolean `is_active`; `Lead`/`Deal`/`Task` use a status/stage
  enum with no explicit "archived" state distinct from their terminal
  values (`converted`, `closed_won`/`closed_lost`, `cancelled`). Not
  wrong — each model's lifecycle genuinely differs — but worth keeping
  in mind for consistency if a 7th model is added later.
- **`Company.is_active` isn't indexed**, despite being a likely filter
  for "active companies" list views. Low impact at any realistic
  near-term data volume; flagging per the Performance Rules' own
  "add indexes based on actual query patterns" rather than adding one
  speculatively now.
- **No index supports "recently created/updated" queries on
  `Company`/`Contact`/`Deal`.** `Lead` and `Activity` both index
  `created_at`; `Company`/`Contact`/`Deal` don't, despite `Deal`'s
  default ordering being `-created_at`. Likely relevant once the
  Dashboard phase needs "recently modified records" — correctly
  deferred for now per the design doc's own stated policy, noting it
  here so it isn't forgotten when that phase starts.

## PostgreSQL-specific opportunities (forward-looking, not action items now)

- The current `btree` indexes on `Company.name`/`Contact.email` accelerate
  exact-match and prefix lookups, not the `icontains`-style fuzzy search
  the Search phase (Phase 5) will likely want. A `pg_trgm` extension with
  `GIN` trigram indexes would be the natural fit when that phase starts —
  not needed yet.
- If DB-level enum strictness (finding #4) is ever wanted, PostgreSQL
  native `ENUM` types are an alternative to `CheckConstraint`s, but make
  adding new choice values a schema migration either way (an `ENUM`
  needs `ALTER TYPE ... ADD VALUE`) — noted as an option, not a
  recommendation, since the current zero-migration-cost `TextChoices`
  approach matches "don't overengineer" better at this stage.

## Comparison against `docs/DATABASE_DESIGN.md`

The implementation matches the design document closely — every field,
relationship, and `on_delete` choice in `apps/crm/models.py` traces back
to a specific line in the design doc, with additions made *during*
implementation (documented in `logs/claude/phase-02-crm-models.md` and
already reflected back into the design doc): the `deal_probability_between_0_and_100`
constraint, and closing the Activity-admin edit path. No field or
relationship contradicts the design doc as it now stands. That said,
"matches the design doc" isn't the same as "every documented invariant
actually holds" — finding #7 above confirms the design doc's own
"application-layer enforcement" framing for Activity immutability is, in
practice, no enforcement at all outside the admin. The design doc was
honest about this being a trade-off; this review's contribution is
confirming empirically how wide that gap still is.

## What's solid (not just problems)

- No unnecessary fields found anywhere — the schema stays lean,
  consistent with the project's "do not overengineer" rule.
- Both multi-column `CheckConstraint`s (`deal_has_company_or_contact`,
  `activity_has_related_object`) and the probability-range constraint
  are correctly implemented and confirmed live in PostgreSQL, not just
  declared in Django.
- Normalization is otherwise solid. `Lead`'s denormalized
  `company_name`/`email`/`phone` fields look like duplication at first
  glance but are a deliberate, already-justified exception (a Lead is
  pre-qualification data with no real Company/Contact to point at yet),
  not an oversight.
- Indexing matches the query patterns the design doc actually
  anticipated; composite/speculative indexes were correctly deferred
  rather than added on guesswork.

## Recommendation

Do not change the schema based on this review alone. Findings #1 and #2
(HIGH) are worth a deliberate decision before Phase 4 (Activities/Tasks
UI) starts building on top of Activity's current CASCADE behavior, since
that's where multi-tagged activities would first become a real feature
rather than a theoretical possibility. Finding #7 (Activity immutability
not actually enforced beyond the admin) is worth resolving in the same
pass, since it touches the same model and the same "is this Activity
data trustworthy" question. The remaining MEDIUM/LOW findings are worth
keeping in mind but don't block Phase 3 (CRM interface) from starting.

**Update, end of Phase 3:** all three (#1, #2, #7) resolved as described
in their own sections above, at the start of Phase 4 as recommended —
`on_delete`'s ORM-only enforcement documented in `CLAUDE.md`, Activity's
relation FKs changed from `CASCADE` to `SET_NULL` with the
`activity_has_related_object` constraint removed, and `Activity.save()`
now rejects updates to existing rows. Verified via
`apps/crm/tests/test_activity.py` and empirical reproduction of each
original finding's scenario, not just re-read and assumed fixed. The
remaining MEDIUM/LOW findings (#3-#6, and the low-severity items) are
still open and still don't block anything — no change to that
assessment.
