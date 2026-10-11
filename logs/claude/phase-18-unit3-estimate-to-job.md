# PHASE 18 UNIT 3: AN ACCEPTED ESTIMATE BECOMES A JOB

Started: 2026-10-09
Ended: 2026-10-09

(Written during the Phase 18 close-out, from PR #149 and the commit.
Unit 3 merged without its own log at the time.)

## Objective

Turn an accepted estimate into a scheduled job without retyping the
work.

## What "one click" can actually mean

A job's start and end times are both required, and only a person knows
them, so a button cannot create the job outright. What the click saves
is the **retyping**.

An accepted estimate gets a "Schedule this work" button. The job form
opens with the customer, the address, the service, the person who sold
it and **every line of work** already filled in. You pick the time. The
saved job links back to the estimate it came from, and the estimate
lists the job it became.

## Two things I got right only after getting them wrong

**The estimate link was silently ignored.** I first put it in the
form's `initial`, where it does nothing, because `quote` is not one of
the form's fields. It is set on save now — which is also the more
honest design: which estimate a job came from is decided by how you
reached the page, not chosen from a dropdown.

**The formset had to be sized to what it is seeded with.** A formset
renders exactly as many blank rows as it is told to, whatever initial
data it is handed, so a two-line estimate asked for one row shows one
and quietly drops the other. That exact bug has already happened in
this project, when invoicing a multi-line job, and the comment on the
shared `line_formset` helper is what reminded me.

## Accepted only, checked in the view

Not merely hidden in the template: a URL can be typed, and booking work
the customer declined is worse than booking work they have not seen.
The estimate is also scoped through `quotes_for`, so one the person may
not see is simply absent rather than refused.

## Verification

| check | result |
| --- | --- |
| Full suite | 1054 pass, 20 new |
| Mutation: ask for one blank row regardless | fails 3 tests |
| Mutation: accept an estimate that is not accepted | fails 1 test |

One process note worth recording. My first full run of this suite
reported a failure in the mixin-placement test from Phase 18.5 unit 5.
That was mine, not the code's: I merged the trunk into the branch
**while the suite was reading the same working tree**, so it imported a
module mid-merge. The run above is a clean one on the settled tree.
Same category of mistake as a mutation check that passes because of the
hour it ran.

No migrations: the job's estimate link has existed since Phase 17.

## Commit

PR #149.
