"""Money figures shared by the dashboard and (Phase 17 unit 3c)
Financials. Every figure is one database aggregate.

Revenue counts *sent* invoices by their issue date: a draft isn't
billed yet, and a voided invoice was never owed.
"""

from django.db.models import Count, Sum, Value
from django.db.models.functions import Coalesce

from .models import LINE_TOTAL, TOTAL_FIELD, ZERO, Invoice, InvoiceLineItem


def invoiced_revenue(first, last):
    """Σ line totals of sent invoices issued between two dates (inclusive)."""
    return InvoiceLineItem.objects.filter(
        invoice__status=Invoice.Status.SENT, invoice__issued_on__range=(first, last)
    ).aggregate(total=Coalesce(Sum(LINE_TOTAL), Value(ZERO), output_field=TOTAL_FIELD))["total"]


def outstanding():
    """Unpaid balance across sent invoices, and how many are unpaid."""
    return (
        Invoice.objects.filter(status=Invoice.Status.SENT)
        .with_balances()
        .filter(balance_amount__gt=0)
        .aggregate(
            total=Coalesce(Sum("balance_amount"), Value(ZERO), output_field=TOTAL_FIELD),
            count=Count("pk"),
        )
    )
