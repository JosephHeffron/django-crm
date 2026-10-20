# OWNER REQUEST: ADD A CUSTOMER FROM THE TASK FORM

Started: 2026-10-17
Ended: 2026-10-19

PR #164, merged as `0e588c1` (`215a9f5` the feature, `8bb611d` the
Sourcery fixes). First of the three usability items the owner asked
for after using the app — Phase 19.5.

## Objective

> "when creating a task, add a create customer button in the 'Who it's
> for' section by the choosing existing customer buttons"

The task form offered a dropdown of existing customers and nothing
else, so a task for somebody not yet on the books meant abandoning the
form. The job form already solved this; the task form never got it.

## Almost nothing needed building

`TaskCreateView.get_initial` already honoured `?contact=`.
`TaskFormUserMixin.chosen_contact()` already resolved POST → saved
record → `?contact=`. `ContactCreateView.get_success_url` already
returned `with_params(target, contact=pk)` for a validated `?next=`.
The whole round trip existed and had no entrance. One context value
(`return_to`) and one button.

## Create only, deliberately

On `TaskUpdateView` there is no `get_initial`, and `chosen_contact()`
reads `self.object.contact` **before** `?contact=` — so the round trip
would come back to a page still showing the old customer, with nothing
to say the new one had been created. The button renders only when
creating (`{% if not object %}`). Making it work while editing is
possible but widens `?contact=` semantics there, and nothing asked for
it.

## The trap next door

On the job form `chosen_contact` is a **pk**; on the task form it is a
**Contact instance**, used for the phone/email line. Copying the job
form's address button, which interpolates `&contact={{ chosen_contact }}`,
would have produced a URL with a `__str__` in it.

## Two of my own tests could not fail

`assertContains(response, reverse("crm:contact_create"))` and
`assertContains(response, "New customer")` are both satisfied by the
nav's Create menu, on every page in the app. They passed whether or
not the form had a button.

Caught because the mirror assertion — `assertNotContains` on the edit
form — reported **3 unexpected matches**. Replaced with
`quick_add_links()`, which matches on the `?next=` only the form's own
button carries.

## Sourcery found a real bug after CI was green

**`ContactForm` exposes `is_active`.** So the quick-add page can create
a customer with that box unchecked. `contact_choices` returns active
customers only, and the create form passed no `chosen`, so the
returned `?contact=` was not among the dropdown's options — while
`chosen_contact()`, an unfiltered `pk=` lookup, named them and printed
their phone. **The page said they were chosen, the browser submitted
nothing for the field, and the task saved with no customer and no
complaint.**

`TaskForm` now keeps `initial["contact"]` choosable as well as
`instance.contact_id`. `get_initial` runs on POST too — the form has no
action, so it posts back carrying `?contact=` — so the option is there
to validate against as well as to render. The escape hatch stays
narrow: one named customer, not every inactive record, asserted in
both directions.

Sourcery's second finding (the button leading to a 403 for someone
holding `add_task` but not `add_contact`) is gated now too. No seeded
role has one without the other — `users/0002`'s `SALES_PERMISSIONS`
grants both — so it needs a hand-edited permission; the gate is one
template condition, so it is worth having anyway.

Note `PropertyForm` and the note form build their contact choices the
same way (`contact_choices(self.instance.contact_id)`) and have the
same exposure if they ever gain a quick-add round trip. Not changed —
neither has one.

## Files changed

- `apps/crm/views.py` — `return_to` in `TaskFormUserMixin`.
- `apps/crm/forms.py` — `TaskForm` keeps the initial contact choosable.
- `apps/crm/templates/crm/task_form.html` — the button, gated on
  `not object and perms.crm.add_contact`.
- `apps/crm/tests/test_task_views.py` — 9 tests.

## Verification

```
python manage.py test        # 1,157 pass
ruff check . && ruff format --check .
python manage.py makemigrations --check
```

Mutation-checked: reverting the choices fix, widening the escape hatch
to every inactive customer, and removing the permission gate are each
caught by exactly the test written for them.
