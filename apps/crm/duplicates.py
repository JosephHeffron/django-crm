"""Spotting a customer who is probably already on the books (Phase 22).

A **warning, never a block.** Two people really can share a name, a
couple really can share a phone number, and a business that cannot add
the second one is worse than one that occasionally holds two records
for the same person. So this finds candidates and the form asks; it
never refuses.

`Contact` has no uniqueness constraint for the same reason, and that is
deliberate (`docs/DATABASE_DESIGN.md`).
"""

import re

from django.db.models import F, Func, Q, Value

from .models import Contact

# The last ten digits, so "585-555-0100", "(585) 555-0100" and
# "5855550100" are one number — and a leading country code does not
# stop a match.
PHONE_DIGITS = 10
_NOT_DIGITS = re.compile(r"\D")


def digits(phone):
    """The comparable part of a phone number, or "" if there isn't one."""
    return _NOT_DIGITS.sub("", phone or "")[-PHONE_DIGITS:]


def _phone_digits_expression():
    """`phone` with everything but digits stripped, in the database.

    PostgreSQL's `regexp_replace`, which this project can rely on
    (ADR 0002: PostgreSQL in development and production, never
    SQLite). Doing it here rather than in Python means the comparison
    stays a query instead of loading every contact to compare by hand —
    the rule against pulling unbounded sets into memory applies to
    duplicate checks too.
    """
    return Func(
        F("phone"),
        Value(r"\D"),
        Value(""),
        Value("g"),
        function="regexp_replace",
    )


def likely_duplicates(first_name="", last_name="", email="", phone="", exclude_pk=None):
    """Contacts that look like the same person as the details given.

    Three independent signals, any one of which is enough to ask about:

    - the same first **and** last name (either alone is far too broad —
      a book of business has several Pats and several Smiths);
    - the same email address, which almost never belongs to two
      customers;
    - the same last ten digits of a phone number.

    Case and surrounding spaces are ignored. Deactivated contacts are
    included on purpose: "you deactivated this person last year" is
    exactly what somebody re-adding them needs to hear.
    """
    first, last = (first_name or "").strip(), (last_name or "").strip()
    address, number = (email or "").strip(), digits(phone)

    match = Q(pk__in=[])  # matches nothing, so an empty form finds nothing
    if first and last:
        match |= Q(first_name__iexact=first, last_name__iexact=last)
    if address:
        match |= Q(email__iexact=address)

    found = Contact.objects.filter(match)
    if number:
        by_phone = Contact.objects.exclude(phone="").annotate(
            phone_digits=_phone_digits_expression()
        )
        # `pk__in` rather than combining into the Q above: the annotation
        # only exists on this queryset, and a subquery keeps it to one
        # statement without a join that could multiply rows.
        found = Contact.objects.filter(
            match | Q(pk__in=by_phone.filter(phone_digits__endswith=number).values("pk"))
        )

    if exclude_pk:
        found = found.exclude(pk=exclude_pk)
    return found.order_by("last_name", "first_name", "pk")


def reasons(contact, first_name="", last_name="", email="", phone=""):
    """Why this contact looked like a duplicate, for the warning text.

    The form says *what* matched rather than just "possible duplicate":
    a shared surname reads very differently from a shared phone number,
    and the person deciding needs to know which it was.
    """
    found = []
    first, last = (first_name or "").strip(), (last_name or "").strip()
    if (
        first
        and last
        and (contact.first_name.lower(), contact.last_name.lower())
        == (
            first.lower(),
            last.lower(),
        )
    ):
        found.append("the same name")
    if email and contact.email and contact.email.lower() == email.strip().lower():
        found.append("the same email")
    if phone and contact.phone and digits(contact.phone) == digits(phone):
        found.append("the same phone number")
    return found
