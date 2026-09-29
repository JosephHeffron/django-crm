"""Repeat-service follow-ups (Phase 17 unit 2c).

A customer is due a follow-up for a service when, for that service's
``followup_interval_months`` (windows ~6, gutters ~6, pressure washing
~12 — owner-editable on the service catalog), neither a completed job
for that service nor any contact touch (an Activity) has happened.

The generator is idempotent and safe to run any number of times a day:
- a DB constraint allows at most one *open* follow-up per customer and
  service;
- a follow-up created after the customer's latest job/touch — whether
  still open, completed, or cancelled ("dismissed") — suppresses a new
  one until a newer job or touch moves the clock again.

Completing a follow-up logs a follow-up Activity (see ``record_completion``),
which is what moves the clock forward.
"""

import calendar
from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.jobs.models import JobLineItem, ServiceType
from apps.users.roles import Role

from .models import Activity, Contact, Task


def add_months(day: date, months: int) -> date:
    """Calendar-aware: Aug 31 + 6 months = Feb 28/29, not an error."""
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


def _fallback_assignee():
    """Who gets a follow-up when the contact has no active owner: an
    Owner-group user, else a superuser."""
    users = get_user_model().objects.filter(is_active=True)
    return (
        users.filter(groups__name=Role.OWNER.value).order_by("pk").first()
        or users.filter(is_superuser=True).order_by("pk").first()
    )


def due_follow_ups(today, contact_ids=None):
    """(contact_id, service_type, baseline_date) for every follow-up due
    on ``today`` — computed with a few aggregate queries, no per-contact
    queries. ``contact_ids`` optionally limits it to those contacts."""
    services = {s.pk: s for s in ServiceType.objects.filter(followup_interval_months__isnull=False)}
    if not services:
        return []

    last_service = (
        JobLineItem.objects.filter(
            job__status="completed",
            job__completed_at__isnull=False,
            service_type_id__in=services,
            job__contact__status=Contact.Status.CUSTOMER,
            job__contact__is_active=True,
        )
        .filter(**({"job__contact_id__in": contact_ids} if contact_ids is not None else {}))
        .values("job__contact_id", "service_type_id")
        .annotate(last=Max("job__completed_at"))
    )
    last_touch = dict(
        Activity.objects.filter(contact__isnull=False)
        .values("contact_id")
        .annotate(last=Max("created_at"))
        .values_list("contact_id", "last")
    )
    latest_follow_up = {
        (row["contact_id"], row["service_type_id"]): row["last"]
        for row in Task.objects.filter(kind=Task.Kind.FOLLOW_UP)
        .values("contact_id", "service_type_id")
        .annotate(last=Max("created_at"))
    }

    due = []
    for row in last_service:
        contact_id, service_id = row["job__contact_id"], row["service_type_id"]
        baseline = max(filter(None, (row["last"], last_touch.get(contact_id))))
        previous = latest_follow_up.get((contact_id, service_id))
        if previous is not None and previous >= baseline:
            continue  # already raised since the last job/touch (open, done, or dismissed)
        service = services[service_id]
        baseline_day = timezone.localdate(baseline)
        if add_months(baseline_day, service.followup_interval_months) <= today:
            due.append((contact_id, service, baseline_day))
    return due


def generate_follow_ups(today=None, contact_ids=None):
    """Create every due follow-up task (optionally only for
    ``contact_ids``); returns the created tasks."""
    today = today or timezone.localdate()
    fallback = _fallback_assignee()
    due = due_follow_ups(today, contact_ids)
    contacts = Contact.objects.select_related("owner").in_bulk({c for c, _, _ in due})
    created = []
    for contact_id, service, baseline_day in due:
        contact = contacts[contact_id]
        owner = contact.owner if contact.owner and contact.owner.is_active else None
        assignee = owner or fallback
        if assignee is None:
            continue  # no active owner anywhere to assign it to
        try:
            with transaction.atomic():
                created.append(
                    Task.objects.create(
                        kind=Task.Kind.FOLLOW_UP,
                        title=f"Follow up: {service.name} — {contact}",
                        description=(
                            f"Last {service.name.lower()} or contact: "
                            f"{baseline_day:%b} {baseline_day.day}, {baseline_day.year}. "
                            f"Due every {service.followup_interval_months} months."
                        ),
                        contact=contact,
                        service_type=service,
                        assigned_to=assignee,
                        created_by=assignee,
                        due_date=today,
                    )
                )
        except IntegrityError:
            # Another run created it between our check and this insert;
            # the partial unique constraint is the real guarantee.
            continue
    return created


def record_completion(task, user):
    """Call when a task becomes completed (any view). Records who did
    it; for a follow-up, logs the contact touch that resets the clock."""
    task.completed_by = user
    if task.kind == Task.Kind.FOLLOW_UP and task.contact_id:
        Activity.objects.create(
            activity_type=Activity.ActivityType.FOLLOW_UP,
            subject=f"Follow-up completed: {task.title}",
            contact_id=task.contact_id,
            created_by=user,
        )
