from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def money(value):
    """Dollars with thousands separators: 1234.5 → "$1,234.50"."""
    if value is None or value == "":
        return "—"
    try:
        amount = Decimal(value).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return value
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


PAYMENT_STATUS_LABELS = {
    "draft": "Draft",
    "void": "Void",
    "paid": "Paid",
    "overdue": "Overdue",
    "partially_paid": "Partially paid",
    "unpaid": "Unpaid",
}


@register.filter
def payment_status(invoice, today):
    """Invoice.payment_status(today) — derived, never stored."""
    return invoice.payment_status(today)


@register.filter
def status_label(value):
    return PAYMENT_STATUS_LABELS.get(value, str(value).replace("_", " ").capitalize())
