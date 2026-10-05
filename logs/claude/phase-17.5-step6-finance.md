# PHASE 17.5 STEP 6: FINANCE

Started: 2026-10-05
Ended: 2026-10-05

## Objective

The Finance side of the reference design (ADR 0010): Invoices,
Payments, Expenses and Profit. Until now the Owner could *read* the
money — Financials computed it from seeded rows — but nothing in the app
could raise an invoice, take a payment, or record a cost. This step
builds those.

## Files created / changed

- `apps/jobs/forms.py` — `InvoiceForm` (job, issue and due dates,
  status, notes; the customer is taken from the job rather than asked
  for, because two fields that must agree are two fields that can
  disagree), `InvoiceLineFormSet` (the shared line editor from step 5),
  `PaymentForm` (amount, date, method, reference — the invoice comes
  from the page, not a field) and `ExpenseForm`.
- `apps/jobs/reports.py` — `INVOICE_FILTERS` and `filter_invoices()`:
  unpaid, overdue, paid, draft, void, all. None of those are stored —
  paid and overdue follow from the payments and the due date — so they
  are expressed as queryset filters against `with_balances()` rather
  than as a column that could drift away from the money. Plus
  `invoice_totals()` for the three cards above the list.
- `apps/jobs/views.py` — `InvoiceListView` (filtered, with totals),
  `InvoiceDetailView`, `InvoiceCreateView` / `InvoiceUpdateView`,
  `PaymentCreateView`, `PaymentListView`, `ExpenseListView`,
  `ExpenseCreateView` / `ExpenseUpdateView`. All Owner-only, matching
  `invoices_for()` and the permissions migration. Opening the invoice
  form from a job starts the bill from that job's own lines. A new
  invoice is dated today and due in `INVOICE_TERMS_DAYS` (14).
- `apps/jobs/models.py` — `Invoice.get_absolute_url()`.
- `apps/core/templatetags/crm_format.py` — the `payment_state` filter,
  so a badge asks the invoice where its money stands instead of reading
  a column.
- Templates — `invoice_list.html`, `invoice_detail.html`,
  `invoice_form.html`, `payment_form.html`, `payment_list.html`,
  `expense_list.html`, `expense_form.html`, `_payment_badge.html`;
  Financials restyled and renamed **Profit** (its "Net" card is now
  "Profit"); "Invoice this job" on a job that has none.
- `apps/core/navigation.py` — the Finance group becomes Invoices,
  Payments, Expenses, Profit; the dashboard's quick actions follow.
- Docs: USER_GUIDE (Invoices, Payments, Expenses, Profit), PERMISSIONS
  (three new rows).
- Tests: `apps/jobs/tests/test_finance.py` (32) — access for all three
  roles, billing a job from its own lines, the customer following the
  job, a due date before the issue date, the filters and their totals,
  recording a full and a part payment, overpayment, a settled invoice,
  expenses with category filtering, and money recorded through the
  pages arriving in Profit.

## Decisions

- **A new invoice starts as a Draft.** Safer than billing on the spot,
  and it matches the existing definition of revenue (a draft isn't
  billed yet). The detail page now says so and points at Edit, so the
  next step is visible rather than guessed.
- **Overpayment is allowed**, and the app says so afterwards. A
  customer rounds up or settles two bills with one check; refusing that
  would make the records lie about what arrived.
- **The page keeps the URL name `financials`** though it's now titled
  Profit. Renaming the route would break existing links and log
  references for no user-visible gain.

## Verification

$ `manage.py test` — 665 tests, OK (633 before, 32 new). No migrations:
  this step adds no fields.
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean.
$ Playwright under production settings, 38 checks, zero CSP violations:
  the Invoices page with its three cards and six filters; billing a job
  from its own lines; a draft explaining itself; recording half the
  balance and seeing "Part paid" in the list, then settling it and
  seeing the button disappear; the Payments total; adding an expense
  and watching the total rise by exactly that amount; filtering by
  category; Profit with its five figures; a Sales Rep and a Cleaner
  refused all four pages and shown no Finance menu; all three pages on a
  phone in light and dark. Every invoice, payment and expense the check
  created was deleted afterwards.

## Errors

- The payment form prefilled `300.0000`. The balance is a sum of sums,
  so it comes back with more decimal places than money has, and a
  browser refuses that against a field stepping in cents. Quantized.
- A form error containing an apostrophe is HTML-escaped, so the test
  matched on a different part of the message (same as step 3).
- Check-script faults, not app faults: the first job picked off the
  calendar already had an invoice (so the button correctly wasn't
  offered), a new invoice is a draft so it had no "Record a payment"
  until the check set it to Sent, and a row-count assertion broke once
  the check had been run three times and left three identical expenses.

## Git

Branch: `feature/restyle-finance`
Commit: pending
Merged to `main`: pending

## Next

Step 7 — Crew: pay rates, working days, Time clock, Assignments,
Payroll, Performance.
