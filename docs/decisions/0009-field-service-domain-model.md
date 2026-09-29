# 0009 — Field-service domain model (folding Lead/Deal into Contact/Quote)

## Context

The original schema (`docs/DATABASE_DESIGN.md`, Phase 2) modeled a
generic B2B sales process: Company → Contact, a separate Lead entity
converted through a dedicated workflow, and a Deal pipeline
(prospecting → negotiation → closed). The business this CRM actually
serves is residential exterior home services: customers are mostly
homeowners with one or more properties, sales happen through **quotes**
built from a **service catalog**, and the work itself is **scheduled
jobs** performed by **crews**, then invoiced. Follow-ups depend on how
long ago a given *service* was last performed (windows every ~6 months,
pressure washing yearly).

## Alternatives considered

- **Keep Lead/Deal and add Quote/Job alongside.** Rejected by the user:
  two overlapping sales pipelines in the UI, and Lead duplicates
  Contact for a business where a lead *is* a person who may become a
  customer.
- **Drop Lead/Deal immediately.** Rejected: dropping models (and any
  data in them) is irreversible; folding first and dropping in a later
  phase leaves a verification window.
- **One generic "Item" model for quotes, jobs, and invoices with a
  type field.** Rejected: the three have different lifecycles and
  fields; separate models with copied line items keep each one simple
  and keep historical documents immutable when prices change.

## Decision

- **Contact** becomes the single person record, with `status`
  (lead / customer / inactive), `lead_source`, and tags. **Property**
  holds addresses (a contact can have several). **Company** is kept,
  optional, for commercial clients such as property managers.
- **Lead → Contact** (`status=lead`) and **Deal → Quote** via a data
  migration (Phase 17 unit 2). Lead and Deal remain in the schema,
  hidden from navigation and read-only, until Phase 18 drops them.
- New `apps.jobs` app: `ServiceType` (catalog; default price, pricing
  unit, per-service follow-up interval, calendar color tone), `Quote` +
  `QuoteLineItem`, `Job` + `JobLineItem` + `JobAssignment` (crew),
  `Photo`, `Invoice` + `InvoiceLineItem` + `Payment`, `Expense`. Line
  items are **copied** quote → job → invoice, so later catalog price
  changes never rewrite history.
- New `apps.messaging` app: `Channel`, `ChannelMembership` (read
  marker), `Message` — shaped so customer SMS can be added later
  (a `customer_sms` channel kind, nullable `author_contact`,
  `transport`/`direction`/`external_id` fields) without a rewrite.
- `Task` gains a `kind` (general / follow_up) and links to service
  type, quote, and job; `Activity` remains the immutable contact-touch
  log that resets follow-up clocks. `BusinessPlan` (+ checklist) and
  `Note` are added in `apps.crm`.
- Derived values (last job date, last contact date, totals, financial
  aggregates, profile stats) are **computed with ORM aggregation**, not
  stored — per `CLAUDE.md`'s "use database aggregation" and "don't
  optimize speculatively" rules.

Full entity detail lives in `docs/DATABASE_DESIGN.md`'s "Field-service
domain (Phase 17)" section.

## Consequences

- Lead/Deal pages and their conversion workflow are retired; `/leads/`
  and `/deals/` redirect to the new equivalents once unit 2 lands.
- `Pillow` becomes a dependency (image fields, photo downscaling and
  EXIF-GPS stripping).
- Financials, follow-ups, and profile stats all read from one source of
  truth (jobs, invoices, payments, activities) rather than separately
  maintained counters.

## Date

2026-09-28
