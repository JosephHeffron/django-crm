# PHASE 20: MONEY — PAYMENT ON THE JOB, REVENUE FROM FINISHED WORK

Started: 2026-10-22
Ended: 2026-10-25

PRs #171 (guards + ADR), #172, #173, #174 and the close-out.
ADR: `docs/decisions/0013-payment-on-the-job-revenue-from-completed-work.md`.

## What the roadmap said, and what was true

The entry read: *"Invoices from completed jobs, payments, expenses, the
Owner-only Financials page (daily/weekly/monthly/YTD, by service and by
rep, server-rendered SVG charts), profile stats hardening."*

A verification pass ran before any code, as the previous three phases
taught. **16 mutations, 12 caught.** Most of the phase was built and
genuinely tested: the presets, the custom-range validation, the
Owner-only gate, revenue's filters, net, the charts, the breakdowns.
"Profile stats hardening" had already been delivered as the role stats
sheet (#158). Four figures had nothing holding them, and were guarded
in #171 before anything moved:

- `collected` excluding payments against a VOID invoice
- expenses bounded by the reporting period
- the average invoice rounded to money
- `jobs_completed` reading `completed_at` rather than `status`

`FigureTests`' fixture was why all four hid: no payment on a void
invoice, no expense outside the window, a revenue dividing evenly
(250 over 2), and no completed jobs at all.

## What mutation testing could not find

Every revenue figure came from `InvoiceLineItem` rows whose invoice was
`SENT`, and `Payment.invoice` was a **required** foreign key whose only
app route was `invoices/<pk>/payments/new/`.

So for a business that takes payment **before** completion and issues
no invoices — which is this one, stated by the owner on 2026-10-13 and
again on 2026-10-22 — the Financials page would report **zero revenue
however much work was sold and paid for, with nowhere to record the
money at all.** Not a bug in any one place; the model asked for a
document the business does not produce.

Measured before deciding: 93 payments (all with an invoice), 97
completed jobs, **2** never invoiced and invisible as revenue, **2**
sent invoices whose job was not complete and counted as revenue.

## The four units

1. **`Payment.job` required, `Payment.invoice` optional** (#172). Money
   recorded from the job page. Hand-written three-step migration —
   add nullable, fill from `invoice.job`, tighten — which ran on 93
   real rows with 0 disagreements. `Payment.save()` derives the job
   when only the invoice is given, which kept the demo seed, the admin
   inline and eighteen test call sites working without edits.
2. **Revenue is completed work** (#173), dated by `completed_at`,
   everywhere a figure is shown — including the monthly revenue goal,
   which was measuring invoices and would have disagreed with the page
   it is judged against.
3. **Outstanding is finished work nobody has paid for** (#174), aged by
   how long ago it was finished. Normally empty here, so it is an
   exception report and says so.
4. **The edges**: the demo seed takes payment the way the business does
   (against the job, on or before the day it was done), and
   `USER_GUIDE`, `DATABASE_DESIGN`, `PERMISSIONS`, `ROADMAP` and
   `CHANGELOG` describe the model that shipped.

`Invoice` is kept and demoted. It drives no figure and remains for the
customer who asks for one. Deleting it would have been irreversible and
it holds real history.

## The nullable foreign key, three times

Making `Payment.invoice` nullable put a NULL on the far side of three
different filters, and each one is a place money could vanish with
nothing on screen to show it.

1. `summary()`'s `.exclude(invoice__status=VOID)` compiled to an
   **INNER JOIN** while the column was `NOT NULL`, which would have
   dropped **every** job payment from "collected". Django widens it to
   a LEFT JOIN with an `IS NOT NULL` guard once the field is nullable,
   so the code was already right — but nothing rendered would show the
   difference, so it has a test on both sides now.
2. The invoice page's "already received on this job" figure excludes
   payments belonging to this invoice, and had to keep the ones with no
   invoice at all.
3. `JobQuerySet.with_balances` now excludes payments against a voided
   invoice (below), and had to keep the same NULL rows.

**The lesson:** the join type depended on `null=True` being set, so the
behaviour could not be settled before the migration. Checking the
generated SQL answered it; a test is what holds it.

## Findings from review, with money attached

Sourcery reviewed every unit. Three findings were worth real money:

- **An invoice raised after a job payment showed the full balance due**,
  counting none of what the customer had paid — an invitation to bill
  twice. The invoice page now reports what the job has received outside
  that invoice. Reported rather than folded into the balance, because a
  job can carry two invoices and counting one payment in both is a
  different wrong answer.
- **A voided payment settled a job.** `collected` has always excluded
  money on a voided invoice; a job's balance did not, so a job settled
  by a payment later voided looked paid, vanished from the unpaid-work
  report, **and** had its money missing from collected — one job
  described two ways on two pages.
- **The admin could mark a job completed and leave `completed_at`
  blank**, producing work worth nothing, or cancel a completed job and
  leave the date behind. `JobAdmin.save_model` stamps now, with the
  same helper every other path uses.

Also fixed: the payment save and its audit entry were not one
transaction (a failed audit left the money saved and invited a second
entry); `Payment.__str__` crashed for a payment with no invoice;
`seed_demo --reset` left job-only payments behind and then failed on
`PROTECT`; and `_unpaid()` required `completed_at`, which **hid debt**
rather than filing it awkwardly.

Three declined, consistently and with the reasoning recorded in the
code: read skew between separate aggregates (three threads, same
answer — the fix is REPEATABLE READ, not a rewrite), expand-and-contract
deployment (this is a single-container systemd deploy), and the shared
test password constant.

## Tests of mine that could not fail

Six, in four units. This keeps happening and the cause is always the
same: a fixture where two different explanations give the same number.

- The payment form's opening amount, checked on a job with nothing
  paid — where "what's left" and "the full value" are equal.
- `test_renders_every_preset_and_explains_a_bad_range` built a job with
  `status=COMPLETED` and no `completed_at`, so after unit 2 it earned
  nothing — and the `$175.00` it asserted was coming from the
  unpaid-invoice table lower down the page.
- `test_a_draft_invoice_is_not_revenue` became trivially true once its
  job had no line items.
- The aging ordering test, where the oldest job was also the largest
  balance, so sorting by money looked like sorting by date.
- My migration test called the reverse guard **directly**, so rewiring
  the operation to `RunPython.noop` left everything green.
- The dashboard revenue test could not tell the status filter from the
  date filter, because its excluded job had a null `completed_at`.

## An invariant nothing was holding

Removing `status=COMPLETED` from the revenue query changed no test,
because `completed_at` is cleared whenever a job leaves that status —
so it looked like dead code. It is not: the admin writes a job
directly, so a **cancelled job can keep its completion date**, and
without that filter cancelled work counts as money earned.

## Method notes

- **`--parallel` is unusable for mutation testing here.** A failing
  test whose traceback cannot be pickled crashes the runner with
  `TypeError: cannot pickle 'traceback' object` instead of printing
  `FAIL:` lines, and a regex over the output reads that as a clean
  run. Sixteen mutations "survived" that way before a hand-run control
  exposed it. **Verdicts now come from the process exit code.**
  Parallel stays useful for a green suite: 1,262 tests in 4m50s
  against 14 minutes.
- Nine mutation harnesses were written across the phase; **five had
  bugs of their own** — anchors that matched nothing after `ruff
  format` reflowed them, anchors that matched four places, a mutation
  that changed a grouping key while leaving the display fields, and
  two that removed a filter a second filter already covered. Every
  harness asserts its anchor matched exactly once before applying.
- `pkill -f 'manage.py test'` matched the shell running it and killed
  the command. Kill by PID.

## Browser pass (production settings, real CSP)

3 roles × 5 money pages × 3 widths: no CSP violations, no console
errors, no sideways scroll, and the Owner-only pages return 403 to the
other two. Then by hand in the browser: the Financials page reads
"Unpaid finished work" and no longer says "unpaid invoice"; the job
page's Payments section opens the form at what is left to pay; saving
returns to the job with the payment on it; a cleaner gets 403 and sees
no button.

**Two of the three "failures" in the first run were the harness.** It
read the Owner-only 403s as console errors (18 of them), and
`button[type=submit]` matched the nav's **logout** button, which logged
the pass out and reported the app as failing to save.

## Verification

```
python manage.py test        # 1,265 pass (1,226 before the phase)
ruff check . && ruff format --check .
python manage.py makemigrations --check
pre-commit run --all-files   # 10 hooks
pip-audit -r requirements.txt
```

## What is left

- A payment still **cannot be corrected** (`jobs.change_payment` has no
  view). That mattered less when a payment was a line under an invoice;
  it is now the primary record of money, so it matters more.
- Invoices remain reachable and undocumented as "optional" anywhere in
  the UI itself — the guide says it, the pages do not.
- A **future** `completed_at` counts as revenue in the current period
  and lands in the first aging bucket. Bad data rather than a bug, and
  the real fix is refusing it where it is written.
