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
import logging
from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.core.models import Notification
from apps.core.notifications import notify
from apps.jobs.models import JobLineItem, ServiceType
from apps.users.roles import Role

from .models import Activity, Contact, Task

logger = logging.getLogger(__name__)


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

    only = {"contact_id__in": contact_ids} if contact_ids is not None else {}
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
        Activity.objects.filter(contact__isnull=False, **only)
        .values("contact_id")
        .annotate(last=Max("created_at"))
        .values_list("contact_id", "last")
    )
    latest_follow_up = {
        (row["contact_id"], row["service_type_id"]): row["last"]
        for row in Task.objects.filter(kind=Task.Kind.FOLLOW_UP, **only)
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


def generate_follow_ups(today=None, contact_ids=None, skipped=None):
    """Create every due follow-up task (optionally only for
    ``contact_ids``); returns the created tasks.

    ``skipped`` is an optional list the caller may pass in to collect
    ``(contact, service)`` pairs that were **due and not created**,
    because there was nobody to assign them to — no active owner on the
    contact and no active Owner-group user or superuser to fall back
    to. An out-parameter rather than a changed return type, because
    fifteen call sites and the demo seed already treat the return value
    as the list of created tasks.

    Collecting them matters more than it looks. Without it the daily
    command reports ``Created 0 follow-up task(s)`` and exits 0 for a
    run that silently dropped work, and systemd records a healthy run —
    exactly the "broken looks healthy" failure
    ``docs/ADMIN_GUIDE.md`` warns about for this timer. Found by review
    of Phase 19's own close-out, which had just described that failure
    mode without noticing this instance of it.
    """
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
            # Nobody to give it to: no active owner on the contact and
            # no active Owner-group user or superuser either. Logged so
            # the journal shows it, and collected so the caller can
            # fail rather than report a healthy zero.
            logger.warning(
                "Follow-up for %s (%s) is due and has no assignee: no active owner "
                "on the customer and no active Owner-group user or superuser.",
                contact,
                service.name,
            )
            if skipped is not None:
                skipped.append((contact, service))
            continue
        try:
            with transaction.atomic():
                task = Task.objects.create(
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
                created.append(task)
                # The key stops a second run announcing the same task
                # again (this generator runs daily and is idempotent).
                notify(
                    assignee,
                    Notification.Kind.FOLLOW_UP,
                    f"Follow-up due: {service.name}",
                    str(contact),
                    task.get_absolute_url(),
                    event=f"task:{task.pk}",
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
            # The timeline already shows the type and the contact.
            subject=f"Checked in about {task.service_type.name.lower()}"
            if task.service_type_id
            else task.title,
            contact_id=task.contact_id,
            created_by=user,
        )
