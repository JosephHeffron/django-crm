# Permissions

Phase 6 unit 2 — a practical role/permission model, per the roadmap.
`docs/SECURITY_REVIEW.md` (Unit 1) flagged that every authenticated
user could do everything; `docs/DATABASE_DESIGN.md` had
already deferred role-based permissions to exactly this phase
("Role-based permissions are planned via Django's built-in Groups/
Permissions in the later Permissions phase"). This follows through on
that plan — no custom permission model, no new app, no new tables:
Django's own built-in `auth` Groups and per-model permissions.

## The model

Three tiers, not a full role hierarchy — kept deliberately small:

1. **Superuser** (`is_superuser=True`) — full access to everything,
   including the Django admin and user/group management itself.
   Django's own built-in behavior (`has_perm()` always returns `True`
   for a superuser); nothing to build here.
2. **Staff group** — day-to-day CRM users who need to create and edit
   records. Membership is managed the same way any Django Group
   membership is: through the admin's User change form, by a
   superuser. No custom "assign role" UI — that would duplicate what
   the admin already does for free.

   **Not the same thing as `User.is_staff`.** Django's own `is_staff`
   field is a separate, orthogonal concept — it only controls whether
   an account can log into `/admin/` at all. A user can be in the
   "Staff" Group (full CRM add/change access) with `is_staff=False`
   and never touch the admin site; equally, `is_staff=True` grants no
   CRM permissions by itself. The name overlap is coincidental — worth
   spelling out explicitly here so it isn't a source of confusion for
   whoever manages users later.
3. **Everyone else (logged in, no group)** — implicitly read-only.
   Not a Group at all — the *absence* of Staff membership already
   means "no add/change permission," so there's nothing to define for
   this tier beyond "don't put someone in Staff yet." A logged-in user
   with no group can still see every list/detail page (see Scope,
   below) but gets a 403 on any create/edit/deactivate/complete/
   convert action.

This intentionally does **not** attempt row-level ("my records only")
permissions, a formal admin/manager/rep hierarchy, or a UI for
managing roles beyond what the Django admin already provides — none of
that is a demonstrated requirement yet, and Django's Group/Permission
system plus `PermissionRequiredMixin` already covers the actual need
("can this signed-in user create/edit CRM records, or only look at
them") without inventing anything.

## Scope: what's gated, what isn't

**Gated** (requires the matching Django model permission via
`PermissionRequiredMixin`): every Create/Update/Deactivate/Complete/
Convert view.

**Not gated** (unchanged — `LoginRequiredMixin` only, as it's always
been): every List/Detail view, the dashboard, and search. Visibility
is deliberately left alone in this unit — this CRM's "single shared
workspace" design (established since Phase 2/3: no per-owner
restriction on who can *see* a Company/Contact/Lead/Deal) isn't being
changed here, only who can *write*. Restricting read access would be a
bigger, separate design question (would "Contacts" need a whole
different visibility rule than "Deals"? Would `owner` become a real
access-control field instead of just a label?) that nothing today
asks for.

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
- **`view_<model>` permissions are never checked.** Django creates
  them automatically for every model, but since visibility isn't
  restricted in this unit (see Scope above), nothing in the app
  queries them. They exist; they're just unused by design, not an
  oversight.

## Seeding the Staff group

A Django data migration
(`apps/crm/migrations/0005_seed_staff_group.py`) creates the "Staff"
group and attaches exactly the permissions the table above requires:
`add_company`, `change_company`, `add_contact`, `change_contact`,
`add_lead`, `change_lead`, `add_deal`, `change_deal`, `add_task`,
`change_task`, `add_activity` — 11 permissions, all on `crm.*` models.

A migration (not a management command run manually, and not "just
document it and expect an admin to click it together by hand") because
this needs to exist consistently and repeatably in every environment
(dev, a future staging/production) the same way the schema itself
does — the same reasoning already applied to seeding the schema itself
in Phase 2, just for reference data instead of tables.

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

- No row-level/per-owner permissions — `owner` stays a label field, not
  an access-control field. Revisit only if a concrete multi-team need
  shows up.
- No custom "assign a role" UI — Group membership is managed through
  the Django admin, which already does this.
- No change to who can *see* records — see Scope above.
- No permission distinction between the six CRM models beyond what the
  table above lists (e.g. no "Task-only" role) — nothing today asks
  for that granularity, and adding it speculatively would be exactly
  the kind of overengineering CLAUDE.md's architecture rule warns
  against.
