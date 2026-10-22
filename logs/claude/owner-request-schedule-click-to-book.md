# OWNER REQUEST: BOOK A JOB BY CLICKING THE SCHEDULE

Started: 2026-10-19
Ended: 2026-10-19

PR #166, merged as `50748b5` (`2d101fa` the feature, `9b6898b` the
Sourcery fixes). Third of the three (Phase 19.5).

## Objective

> "in the main schedule, have it be able to click any day of the week
> and create a job from clicking the day, and having the times of the
> day be clickable to add that new job (intervals of 30min)"

Clicking a day's number went to that day; clicking anywhere else in
the cell did nothing. The day view was a flat agenda with no times to
click. The only date-aware **New job** link was the hero button, on
the day view alone.

The owner's answers shaped it: week and month clicks **jump to that
day's schedule** rather than straight to the form; the day view gets
**30-minute slots** across **6am–8pm**; a new job defaults to **two
hours**; a slot that already has a job is **marked busy but still
clickable**, because two crews can be out at once.

## 6am–8pm is a floor, not the window

A fixed window would lie. An event at 05:30 is grouped onto the day
and listed in the agenda above, so a grid showing 06:00 as the start
of the day would contradict the same page. The window widens to take
in the earliest and latest booking, clamped to the local day, and
starts are floored onto the half-hour grid.

## Overlap is half-open at both ends

`start < slot_end and end > slot_start`. A job ending at exactly 11:00
must not mark the 11:00 slot: with `<=` every back-to-back booking
paints an extra half hour. **A rendered page looks plausible either
way**, which is why this has a test of its own rather than an eyeball.

A site visit has `end=None` and would read as free, so an open-ended
event holds the one slot it starts in.

## The cell link: a stretched pseudo-element, not an anchor

The first design added a flex-grow filler anchor per cell. Rejected:
it covers only leftover space, so gaps between chips stay dead, and it
adds a second anchor per cell — **42 extra tab stops on the month
view**.

Instead `.cal-day-head::after` / `.cal-date::after` stretch the anchor
that is already there, with `position: relative` on the cell and on the
chips. The cells cannot be wrapped in an anchor: they hold event chips
that are anchors themselves, and they are drag drop targets. A
pseudo-element is never an event target, so `reschedule.js`'s
`closest("[data-day]")` resolves exactly as before. CSS only, no
template change, and it applies to every role — it just navigates to a
day everyone can already open.

## Two live bugs fixed on the way

1. **`JobRescheduleView.post` was a 500.** It passed
   `parse_datetime`'s result straight to `move_job`, and
   `parse_datetime` **raises** `ValueError` on a well-formed
   impossibility (`2026-02-30T09:00`) rather than returning None, and
   returns an **aware** datetime when the value carries an offset,
   which then makes `make_aware` raise in its turn. Anyone who could
   reach the move controls could crash the request by editing the
   field. Found while writing the same guard for the new `?start=`.

2. **`.calendar-day.is-drop-target` matched nothing.** No template has
   ever rendered that class — it is `.cal-day` on the week view and
   `.cal-cell` on the month view — so the drag-target outline had
   never once shown.

## A wrong reason, recorded rather than quietly fixed

The module comment said the grid is built in naive local time because
adding a timedelta to an aware datetime drifts an hour across a DST
change. **It does not.** `zoneinfo` datetimes add to their naive
fields, so an aware grid steps by wall clock too — mutating
`_local_naive` to leave them aware passes every test in `DaySlotTests`.

The real reasons are that the value each slot hands the form is a
naive local string, and that comparing on the wall clock keeps the
busy flags matching the labels beside them. Both the comment and the
DST test's docstring now say so. The first version of that test was
also pinned to 6am–8pm, which sails straight over a 2am transition and
would have passed either way; it now drags the floor down to midnight
with an early event.

One edge is accepted rather than solved, and documented: on the
spring-forward morning 2:00–3:00am does not exist locally, so a slot
labelled 2:30 AM would open the form at another time. The grid only
reaches down there if a booking already sits at 2am on that one night.

## The grid goes below the agenda

Put in place of the empty state, "Nothing scheduled" stops being true
and `test_scheduling.py`'s assertion on an empty day breaks. It sits
under its own heading, below.

Slot links carry `?start=` only. Adding `&crew=` would be accepted by
the URL and silently ignored by the form.

## Browser pass (production settings, real CSP)

The harness lives outside the repo and had been swept from `/tmp`
again; recreated (`csp_test_settings.py` plus a Playwright script in
the scratchpad). Playwright's browsers were still cached, the Python
package was not.

Owner / Sales Rep / Cleaner × day/week/month × 1280/834/390px: no CSP
violations, no console errors, no horizontal overflow. Then the things
tests cannot see:

| Check | Result |
|---|---|
| Dead space in a week cell | opens that day |
| Dead space in a month cell | opens that day |
| A chip on either view | still opens its job |
| Dragging a chip to another day | still reschedules |
| 7:30 AM slot | form opens 07:30 → 09:30 |
| A busy slot | still books |
| Cleaner | no slot grid at all |

**Three "failures" in the first run were the harness, not the app.**
`page.mouse.click` dispatches a raw input event and returns, so
`wait_for_load_state()` looked at the page that was already loaded and
said yes; `Locator.click()` auto-waits, which is why the chip checks
passed and these did not. And one probe point was 70px below the fold,
where `elementFromPoint` returns null. Diagnosed with
`elementFromPoint` before changing any application code — the stretch
was working the whole time.

Dev data was left as found: three throwaway users created for the pass
were deleted (after their `JobAssignment` rows — `on_delete=PROTECT`),
and the dragged job was dragged back.

## Files changed

- `apps/jobs/calendar.py` — `SLOT_MINUTES`, `DAY_OPENS_AT`,
  `DAY_CLOSES_AT`, `day_slots()` and two rounding helpers.
- `apps/jobs/views.py` — `_parse_start`; `?start=` on
  `JobCreateView.get_initial`; the reschedule fix; `slots` in the day
  view's context, gated on `can_schedule`.
- `apps/jobs/templates/jobs/calendar.html` — the slot grid.
- `static/css/base.css` — the stretched day link, the slot grid, the
  drop-target fix.
- `apps/jobs/tests/test_calendar.py` (12), `test_scheduling.py` (9),
  `test_reschedule.py` (2).

## Verification

```
python manage.py test        # 1,181 pass on this branch
                             # (1,196 on main once #165 was in)
ruff check . && ruff format --check .
python manage.py makemigrations --check
```

21 mutations, every one caught by the test written for it.
