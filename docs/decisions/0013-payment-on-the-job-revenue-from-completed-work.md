# 0013 — Payment belongs to the job, and revenue is completed work

## Context

This business takes payment **before** a job is completed. The owner
said so on 2026-10-13, and again on 2026-10-22: *"record the payment
on the job itself. completed jobs should update the records
financials."*

The schema does the opposite. ADR 0009 modeled the money side as
`Invoice` + `InvoiceLineItem` + `Payment`, with billing after the work,
and Phase 20's verification pass (2026-10-22) measured what that costs
a business that does not invoice:

- **Every revenue figure comes from sent invoices.** `invoiced_revenue`
  sums `InvoiceLineItem` rows where `invoice.status = SENT`, and the
  Financials headline, the trend chart, revenue-by-service,
  revenue-by-rep and the average invoice are all built on it. The
  dashboard's revenue cards use the same function.
- **`Payment.invoice` is a required foreign key**, and the only
  app-facing route to creating one is `invoices/<pk>/payments/new/`.
  (`PaymentInline` on `InvoiceAdmin` is a second path, through the
  Django admin, which is not where the business works.)

Together: with no invoices there is **no revenue on the Financials page
however much work is sold and paid for, and nowhere to record the money
at all.** Not a bug in any one place — the model asks for a document
this business does not produce.

The roadmap's Phase 20 line, "invoices from completed jobs", was never
implemented either: `InvoiceForm` offers every job including cancelled
ones. The code matched the business more closely than the roadmap did.

Measured on this install before deciding, so the size of the change is
known rather than guessed:

| | Count |
|---|---|
| Payments | 93 — **every one** has an invoice, and every invoice has a job, so nothing is orphaned by the migration |
| Invoices | 98, of which 95 sent |
| Completed jobs | 97 |
| Completed jobs **never invoiced** (value invisible as revenue today) | 2 |
| Sent invoices whose job is **not** completed (counted as revenue today, would stop) | 2 |

So the revenue figures move in both directions, by a little, on this
data. On an install that stops invoicing altogether they would move by
everything, which is the case this ADR exists for.

## Alternatives considered

- **Keep invoices and reframe them as the record of an up-front
  payment**, issued when a job is booked. Smallest change, and
  Financials would keep working untouched. Rejected by the owner: it
  still requires producing a document per job for a business that has
  said it does not need one. It also leaves every figure one step
  removed from the thing it describes.
- **Leave the money model alone and spend Phase 20 on the gaps already
  recorded** (a payment cannot be corrected, an expense cannot be
  deleted, a service cannot be added). Rejected: those are real but
  small, and they leave the Owner's financial picture reading zero in
  real use.
- **Delete `Invoice`, `InvoiceLineItem` and the invoice pages.**
  Rejected, and deliberately so. Dropping tables is irreversible,
  `Invoice` holds real history in this install, and a customer may
  still ask for a document. Demoting is reversible; deleting is not
  (`CLAUDE.md`: prefer reversible changes).
- **A second revenue definition alongside the first**, switchable by a
  setting. Rejected: two definitions of revenue is two numbers that can
  disagree, which is the defect PR #158 had just finished removing from
  the profile stats.

## Decision

**1. A payment belongs to a job.**

`Payment.job` becomes a required foreign key (`PROTECT`, as
`Payment.invoice` is today). A data migration fills it from
`payment.invoice.job`, which is always present, so no payment is
orphaned and the change is reversible.

`Payment.invoice` becomes **nullable** and optional. It is kept rather
than dropped: where an invoice exists it is the provenance of that
payment, and `Invoice.paid_amount` / `balance_amount` keep reading
their own payments, so invoices behave exactly as they do today. A
payment created from a job simply has no invoice.

Payments are recorded from the **job** page. The invoice route keeps
working and keeps setting both fields.

**2. Revenue is completed work, dated by `completed_at`.**

`completed_revenue(first, last)` sums `JobLineItem` totals for jobs
with `status = COMPLETED` whose `completed_at` falls in the window, and
replaces `invoiced_revenue` as the basis of the Financials summary, the
trend chart, revenue-by-service, revenue-by-rep and the dashboard's
revenue cards.

`completed_at`, not `status` alone, is the date — the rule every other
count of finished work in this app already follows.

**3. What was about invoices becomes about jobs.**

- "Average invoice" becomes **average job value** over the same
  completed jobs.
- "Outstanding" and the aged-balance table become **completed work that
  has not been paid for**: `job.total - Σ payments`, aged by
  `completed_at`. For a business taking payment up front this should
  normally be empty, which makes it a useful exception report rather
  than a routine one.
- `Invoice` keeps its own pages, its nav entry and its figures. It
  drives **no** Financials number after this.

## Reason

The figures should describe the thing the business actually does. A
completed job is the event that earns money here, and a payment is
money against that job; both are facts the app already holds. Routing
them through a document nobody issues is what produced a page reading
zero.

Keeping `Invoice` in place, and keeping `Payment.invoice` as an
optional link, means this is additive at the database level: one new
column, one widened column, and no data destroyed.

## Consequences

- **Revenue figures will change** on any install with invoices whose
  jobs are not completed, or completed jobs that were never invoiced.
  That is the point of the change, and it must be said out loud in the
  release notes rather than discovered.
- **Revenue moves when a job is marked complete**, not when a document
  is sent. Reopening a job (which clears `completed_at`) therefore
  takes its value back out of the period. The existing invariant that
  a reschedule must not touch `status` or `completed_at` becomes
  load-bearing for money, not just for counts.
- A job with no line items is worth nothing, so booking without pricing
  (which the job form allows, by design) shows as completed work worth
  £0 until the lines are filled in.
- `Payment.invoice` being nullable means code that assumed
  `payment.invoice` is present must handle `None`:
  `apps/core/export.py`'s payment export, the payment list, the admin
  inline, and `reports.summary`'s exclusion of payments against VOID
  invoices (which now applies only to payments that have an invoice).
- Two foreign keys that can disagree: a payment could name a job and an
  invoice belonging to a different job. `Payment.clean()` refuses that,
  the way `InvoiceForm` avoids asking for a customer that must match
  the job's. Note the limit of that: a model `clean()` runs through
  forms and `full_clean()`, **not** in the database, and a check
  constraint cannot reach across tables to compare
  `payment.job_id` with `payment.invoice.job_id`. Raw SQL or a
  `QuerySet.update()` can still write a disagreeing pair, the same way
  `on_delete` does not hold outside the ORM
  (`docs/DATABASE_REVIEW.md` finding #1). There are no such writes
  today, and the guard belongs where the data comes in.
- `docs/DATABASE_DESIGN.md` and `docs/USER_GUIDE.md` describe
  invoice-driven money and need revising. `docs/ARCHITECTURE.md` does
  **not** — it has no invoice, payment or reporting content, checked
  rather than assumed after this ADR first listed it. `docs/ROADMAP.md`'s Phase 20 line ("invoices from completed
  jobs") is superseded by this ADR.
- The demo seed creates payments through invoices; it needs to create
  some directly against jobs, or the demo data will not exercise the
  path the business uses.
- Aged balances lose their anchor in `Invoice.due_on` and gain one in
  `completed_at`. "Overdue" stops meaning "past the due date on a
  document" and starts meaning "finished and still unpaid", which is a
  different question with the same shape.

## Date

2026-10-22
