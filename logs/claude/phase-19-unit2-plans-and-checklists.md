# PHASE 19 UNIT 2: PLANS AND CHECKLISTS

Started: 2026-10-11
Ended: 2026-10-11

## Objective

`BusinessPlan` and `PlanChecklistItem` have existed since Phase 17,
with a list page and a detail page — and no way to create or change
either outside the Django admin. `plan_detail.html` carried the line
"Editing plans and ticking off steps arrives in Phase 19".

No migration: every model already existed.

## Ticking is one POST per step

The owner's choice, between that and one form over the whole checklist.
Ticking step two does not resubmit the other fourteen, and it works
with no JavaScript — each step is an ordinary form with its own
endpoint.

The costs are real and both asserted: one request per tick, and one
change-log entry per tick.

**Ticks are recorded in the change log.** Consistent with
`JobStatusView`, which already records a POST-only status change and
says in a comment it is "exactly the kind of change the owner wants a
record of". A fifteen-step plan worked through over a week is fifteen
entries — but the log is paginated and filterable by record type, and a
log that records some writes and not others is worse than a noisy one.
`undo.UNDOABLE_MODELS` does not name the model, so entries are history
rather than something with an Undo button.

## Files created / changed

- `apps/crm/forms.py` — `BusinessPlanForm`, `ChecklistItemForm`.
- `apps/crm/views.py` — `PlanFormMixin`, create/update, and three
  POST-only endpoints: add a step, toggle one, remove one.
- `apps/crm/models.py` — `PlanChecklistItem.get_absolute_url`.
- `apps/crm/templates/crm/plan_form.html` (new), `plan_detail.html`,
  `plan_list.html`.
- `static/css/base.css` — `.checklist-toggle`, `.checklist-remove`, and
  a corrected strike-through selector.
- `apps/crm/tests/test_plans.py` (26).

## Three things found by reading rather than assuming

**`icon-clipboard` does not exist.** Invented — the same mistake as the
CSS tokens in Phase 18.5. Every icon in the new templates is now
checked against `templates/partials/_icons.html`.

**The change log would have rendered a broken link.** It renders
`record.get_absolute_url` for every entry and `PlanChecklistItem` had
none. **Django resolves a missing template attribute to the empty
string silently**, so this would have been `<a href="">` — not an
error, just a link that goes nowhere, invisible until clicked. A step
now points at its parent plan.

**My own markup silently broke the existing strike-through.** The rule
was `.checklist li.is-done > span:nth-child(2)` — a *direct* span
child. Moving the step text inside a `<button>` stops that matching, so
done steps would have quietly lost their line-through. Replaced with
`.checklist li.is-done .checklist-text` and confirmed in the browser
via **computed style**, not by reading markup. `.checklist` is used by
this one template, so the change is contained.

Same class of bug as Phase 18.5's `.inline-form`, where a CSS fix never
applied because a later rule shadowed the class name. Reading the
existing CSS before writing any is what caught it.

## The audit's access sweep caught my own omission

`test_every_route_is_either_swept_or_explained` failed on the full
suite with four new routes it could not build arguments for. They would
have fallen out of the signed-out and no-role checks in silence.

Worth stating plainly: **every targeted test run passed**, and this unit
would have been reported as verified. Only the full suite caught it,
because the guard lives in another app's tests. That is the omission
failure mode the sweep was written for, landing on its author three
days later.

## Who can do what

Straight from `users/0004_field_service_permissions`: Owner and Sales
Rep can write plans and work the checklist; a Cleaner gets 403
everywhere, because they hold no `businessplan` permissions at all. A
plan cannot be *assigned* to a crew member either — it would sit on a
page they cannot open — so the owner picker is filtered and the form
rejects it.

Sales reps have `delete_planchecklistitem` but not
`delete_businessplan`, which the views honour: removing a step off your
own list is not discarding the plan.

Removing a step is a real delete, not a flag. A mistyped step is
clutter, not history, and without this a typo would be permanent.

## Verification

```
python manage.py test                   # 1,085 pass, 26 new
ruff / format / makemigrations --check   # clean
```

Browser, production settings, 3 widths: 4 pages, 0 CSP violations, 0
console errors, no sideways scroll. 11 interaction steps, 0 failed —
tick, untick, add, append order, remove, header Save, the two forms
sharing a row, and the strike-through by computed style.

Mutation-checked: removing `get_absolute_url` is caught; dropping the
role guard on the toggle endpoint is caught.

## Commit

PR #155.
