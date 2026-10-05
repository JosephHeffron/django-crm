import zlib
from decimal import Decimal, InvalidOperation

from django import template

from apps.core.business import currency_symbol

register = template.Library()


@register.filter
def money(value):
    """Amount in the business's currency with thousands separators:
    1234.5 → "$1,234.50" (or "CA$1,234.50")."""
    if value is None or value == "":
        return "—"
    try:
        amount = Decimal(value).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return value
    sign = "-" if amount < 0 else ""
    return f"{sign}{currency_symbol()}{abs(amount):,.2f}"


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


@register.filter
def elided_page_range(paginator, number):
    """Page numbers with gaps elided: 1 2 … 7 8 9 … 20."""
    return paginator.get_elided_page_range(number, on_each_side=1, on_ends=1)


AVATAR_COLORS = 5


@register.filter
def avatar_class(name):
    """avatar-c1 … avatar-c5, the same for the same name every time (a
    CRC, not Python's per-process randomized hash)."""
    return f"avatar-c{zlib.crc32(str(name).encode()) % AVATAR_COLORS + 1}"


@register.filter
def initials(user_or_name):
    """Two letters for an avatar: first + last name, else the username."""
    first = getattr(user_or_name, "first_name", "")
    last = getattr(user_or_name, "last_name", "")
    if first and last:
        return (first[0] + last[0]).upper()
    if hasattr(user_or_name, "get_username"):
        return user_or_name.get_username()[:2].upper()
    parts = str(user_or_name).split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return str(user_or_name)[:2].upper()
