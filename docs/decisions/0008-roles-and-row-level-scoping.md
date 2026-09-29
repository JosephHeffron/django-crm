# 0008 — Owner / Sales Rep / Cleaner roles with server-side scoping

## Context

`docs/PERMISSIONS.md` (Phase 6) deliberately built a minimal model:
superusers, one "Staff" group holding add/change permissions, and every
other logged-in user implicitly read-only — with **visibility left
unrestricted** ("no row-level 'my records only' permissions … not a
demonstrated requirement yet").

That requirement now exists. The CRM is being pivoted to the owner's
exterior home-services company (Phase 17, `docs/ROADMAP.md`), whose
users are the Owner, Sales Reps, and Cleaners/crew working from phones.
Cleaners must see only their own schedule and assigned jobs — not the
customer list, quotes, or financials — and Sales Reps must not see
Financials. Hiding links in the UI is not enough: every restriction has
to hold server-side.

## Alternatives considered

- **Keep "Staff" and add per-view `is_staff`/flag checks.** Rejected:
  scatters role logic across views, and "Staff" no longer describes any
  real job in this business.
- **A custom `AUTH_USER_MODEL` with a `role` field.** Rejected: swapping
  the user model this late is disruptive (eight existing FKs to
  `auth.User`), and Django Groups already represent roles well —
  `docs/SECURITY_REVIEW.md` #7 already accepted the default user model.
- **Object-level permission library (e.g. django-guardian).** Rejected:
  a new dependency and per-object permission rows for a scoping rule
  that is simple and structural ("a cleaner sees jobs they're assigned
  to") — a queryset filter expresses that directly.

## Decision

- Three Django **Groups** — `Owner`, `Sales Rep`, `Cleaner` — created by
  a data migration. A superuser always counts as Owner. A user in no
  role group has **no role** and is denied every CRM page (fail closed):
  forgetting to assign a role must never expose customer data.
- `Owner` and `Sales Rep` receive the add/change model permissions the
  old "Staff" group held; existing Staff members become Sales Reps and
  the Staff group is removed (reversibly — the migration's reverse
  restores it).
- One module, `apps/users/roles.py`, owns the role logic:
  `user_role(user)`, the `Role` enum, role sets (`SALES_ROLES`,
  `ALL_ROLES`), and `RoleRequiredMixin` (403 for an authenticated user
  whose role isn't allowed). Navigation (`apps/core/navigation.py`) is
  built from the same role declarations, so a nav link and the page it
  points to can't disagree about who may see it.
- Row-level scoping (a cleaner's own jobs, etc.) is done with queryset
  helpers in `roles.py` used by every relevant view. An object outside
  the user's scope returns **404**, not 403, so its existence isn't
  revealed.
- `PermissionRequiredMixin` stays on write views as defense in depth.

## Consequences

- `docs/PERMISSIONS.md`'s "visibility unrestricted" and "read-only
  tier" statements are superseded; that document is updated to match.
- Existing tests that log in a group-less user and expect `200` on CRM
  pages must grant a role — they now test the Sales Rep path, which is
  what they were effectively testing as "Staff".
- Adding a page means declaring its allowed roles once (view mixin +
  nav entry) — the access-matrix test enumerates every route × role, so
  an undeclared page fails CI rather than silently being open.

## Date

2026-09-28
