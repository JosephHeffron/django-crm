"""Small builders for jobs-app tests (leading underscore: not a test
module). Kept explicit rather than a factory library — the project
has no test-data dependency and doesn't need one for this."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.crm.models import Contact
from apps.jobs.models import (
    Invoice,
    InvoiceLineItem,
    Job,
    JobAssignment,
    JobLineItem,
    Quote,
    QuoteLineItem,
    ServiceType,
)

User = get_user_model()


def user(username="owner", **extra):
    return User.objects.create_user(username, password="correct-horse-battery", **extra)


def contact(created_by, first="Pat", last="Homeowner", **extra):
    return Contact.objects.create(first_name=first, last_name=last, created_by=created_by, **extra)


def service(slug="gutter-cleaning"):
    # Seeded by jobs/0002_seed_service_catalog.
    return ServiceType.objects.get(slug=slug)


def aware(year, month, day, hour=9):
    return timezone.make_aware(datetime(year, month, day, hour))


def job(contact, created_by, start=None, hours=2, lines=((Decimal("1"), Decimal("175")),), **extra):
    start = start or aware(2026, 10, 1)
    svc = extra.pop("primary_service_type", None) or service()
    j = Job.objects.create(
        contact=contact,
        created_by=created_by,
        primary_service_type=svc,
        scheduled_start=start,
        scheduled_end=start + timedelta(hours=hours),
        **extra,
    )
    for qty, price in lines:
        JobLineItem.objects.create(job=j, service_type=svc, quantity=qty, unit_price=price)
    return j


def assign(job, crew_member, hours=None):
    return JobAssignment.objects.create(job=job, user=crew_member, hours_worked=hours)


def quote(contact, prepared_by, lines=((Decimal("1"), Decimal("100")),), **extra):
    q = Quote.objects.create(contact=contact, prepared_by=prepared_by, **extra)
    for qty, price in lines:
        QuoteLineItem.objects.create(
            quote=q, service_type=service(), quantity=qty, unit_price=price
        )
    return q


def invoice(job, lines=((Decimal("1"), Decimal("175")),), issued=date(2026, 10, 2), **extra):
    extra.setdefault("status", Invoice.Status.SENT)
    inv = Invoice.objects.create(
        job=job,
        contact=job.contact,
        issued_on=issued,
        due_on=issued + timedelta(days=14),
        **extra,
    )
    for qty, price in lines:
        InvoiceLineItem.objects.create(
            invoice=inv, service_type=service(), quantity=qty, unit_price=price
        )
    return inv
