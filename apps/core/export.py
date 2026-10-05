"""Owner data export (Business Settings → Export Data): one dataset at a
time as CSV (opens in Excel) or JSON, streamed so a large table never
sits in memory.

CSV cells that a spreadsheet would treat as a formula (starting with
=, +, -, @, tab, or carriage return) are prefixed with an apostrophe, so
a customer named "=HYPERLINK(...)" can't run anything when the file is
opened (CSV/formula injection). Passwords and hashes are never exported.
"""

import csv
import json

from django.contrib.auth import get_user_model
from django.db.models import Prefetch

from apps.crm.models import Company, Contact, Property
from apps.jobs.models import Expense, Invoice, Job, Payment, Quote
from apps.users.roles import roles_for

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _iso(value):
    return value.isoformat() if value else ""


def _name(user):
    return (user.get_full_name() or user.get_username()) if user else ""


def _customers():
    rows = Contact.objects.select_related("company", "owner").prefetch_related(
        "tags", Prefetch("properties", queryset=Property.objects.filter(is_primary=True))
    )
    for c in rows.order_by("pk").iterator(chunk_size=500):
        primary = next(iter(c.properties.all()), None)
        yield {
            "id": c.pk,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "stage": c.status,
            "email": c.email,
            "phone": c.phone,
            "company": c.company.name if c.company else "",
            "address": str(primary) if primary else "",
            "lead_source": c.lead_source,
            "tags": ", ".join(sorted(t.name for t in c.tags.all())),
            "owner": _name(c.owner),
            "active": c.is_active,
            "created": _iso(c.created_at),
        }


def _companies():
    for c in Company.objects.order_by("pk").iterator(chunk_size=500):
        yield {
            "id": c.pk,
            "name": c.name,
            "phone": c.phone,
            "industry": c.industry,
            "active": c.is_active,
            "created": _iso(c.created_at),
        }


def _jobs():
    jobs = (
        Job.objects.with_totals()
        .select_related("contact", "primary_service_type", "sales_rep")
        .prefetch_related("crew")
        .order_by("pk")
    )
    for j in jobs.iterator(chunk_size=500):
        yield {
            "job": j.number,
            "customer": str(j.contact),
            "service": j.primary_service_type.name,
            "status": j.status,
            "scheduled_start": _iso(j.scheduled_start),
            "scheduled_end": _iso(j.scheduled_end),
            "completed_at": _iso(j.completed_at),
            "total": str(j.total),
            "sales_rep": _name(j.sales_rep),
            "crew": ", ".join(_name(u) for u in j.crew.all()),
            "rating": j.customer_rating or "",
        }


def _quotes():
    quotes = Quote.objects.with_totals().select_related("contact", "prepared_by").order_by("pk")
    for q in quotes.iterator(chunk_size=500):
        yield {
            "estimate": q.number,
            "customer": str(q.contact),
            "status": q.status,
            "total": str(q.total),
            "prepared_by": _name(q.prepared_by),
            "created": _iso(q.created_at),
            "sent": _iso(q.sent_at),
            "accepted": _iso(q.accepted_at),
            "expires": _iso(q.expires_on),
        }


def _invoices():
    invoices = Invoice.objects.with_balances().select_related("contact", "job").order_by("pk")
    for i in invoices.iterator(chunk_size=500):
        yield {
            "invoice": i.number,
            "job": i.job.number,
            "customer": str(i.contact),
            "issued": _iso(i.issued_on),
            "due": _iso(i.due_on),
            "status": i.status,
            "total": str(i.total),
            "paid": str(i.paid),
            "balance": str(i.balance),
        }


def _payments():
    payments = Payment.objects.select_related("invoice", "recorded_by").order_by("pk")
    for p in payments.iterator(chunk_size=500):
        yield {
            "invoice": p.invoice.number,
            "amount": str(p.amount),
            "received": _iso(p.received_on),
            "method": p.method,
            "notes": p.notes,
            "recorded_by": _name(p.recorded_by),
        }


def _expenses():
    for e in Expense.objects.select_related("recorded_by").order_by("pk").iterator(chunk_size=500):
        yield {
            "date": _iso(e.date),
            "category": e.category,
            "amount": str(e.amount),
            "description": e.description,
            "recorded_by": _name(e.recorded_by),
        }


def _team():
    users = list(get_user_model().objects.order_by("pk"))
    roles = roles_for(users)
    for u in users:
        yield {
            "username": u.get_username(),
            "name": u.get_full_name(),
            "email": u.email,
            "role": roles[u.pk].value if roles[u.pk] else "",
            "active": u.is_active,
            "joined": _iso(u.date_joined),
        }


DATASETS = {
    "customers": ("Customers", _customers),
    "companies": ("Companies", _companies),
    "jobs": ("Jobs", _jobs),
    "estimates": ("Estimates", _quotes),
    "invoices": ("Invoices", _invoices),
    "payments": ("Payments", _payments),
    "expenses": ("Expenses", _expenses),
    "team": ("Team", _team),
}
FORMATS = ("csv", "json")


class _Echo:
    """A file-like object that returns what's written, for streaming."""

    def write(self, value):
        return value


def safe_cell(value):
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def stream_csv(rows):
    writer = csv.writer(_Echo())
    header_written = False
    for row in rows:
        if not header_written:
            yield writer.writerow(list(row))
            header_written = True
        yield writer.writerow([safe_cell(v) for v in row.values()])


def stream_json(rows):
    yield "[\n"
    first = True
    for row in rows:
        yield ("" if first else ",\n") + json.dumps(row)
        first = False
    yield "\n]\n"
