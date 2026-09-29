"""A contact's history in one list (Phase 17 unit 3): activities, jobs,
quotes, notes, and team messages that reference the contact — newest
first.

Each source is capped at TIMELINE_LIMIT before merging, so the merged
list's top TIMELINE_LIMIT is exact without loading unbounded history.
Messages are limited to channels the viewer may read (public channels
and ones they belong to): a direct message between two other people
must not leak onto a contact page.
"""

from dataclasses import dataclass
from datetime import datetime

from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone

from apps.jobs.models import Job
from apps.messaging.models import Channel, Message

from .models import Activity

TIMELINE_LIMIT = 50


@dataclass
class TimelineEntry:
    when: datetime
    kind: str  # activity / job / quote / note / message — also a CSS hook
    label: str
    title: str
    url: str = ""
    detail: str = ""
    by: str = ""  # who, as a display name


def readable_channels(user):
    return Channel.objects.filter(Q(kind=Channel.Kind.PUBLIC) | Q(memberships__user=user)).values(
        "pk"
    )


def _person(user):
    if user is None:
        return ""
    return user.get_full_name() or user.get_username()


def contact_timeline(contact, viewer, limit=TIMELINE_LIMIT):
    now = timezone.now()
    entries = [
        TimelineEntry(
            when=activity.created_at,
            kind="activity",
            label=activity.get_activity_type_display(),
            title=activity.subject,
            detail=activity.description,
            by=_person(activity.created_by),
        )
        for activity in contact.activities.select_related("created_by")[:limit]
    ]
    # Jobs that have started; upcoming work is shown separately.
    jobs = (
        contact.jobs.filter(scheduled_start__lte=now)
        .select_related("primary_service_type")
        .order_by("-scheduled_start", "-pk")[:limit]
    )
    entries += [
        TimelineEntry(
            when=job.completed_at or job.scheduled_start,
            kind="job",
            label=f"Job {job.get_status_display().lower()}",
            title=f"{job.number} · {job.primary_service_type.name}",
            url=job.get_absolute_url(),
        )
        for job in jobs
    ]
    entries += [
        TimelineEntry(
            when=quote.created_at,
            kind="quote",
            label=f"Quote {quote.get_status_display().lower()}",
            title=quote.number,
            url=quote.get_absolute_url(),
            by=_person(quote.prepared_by),
        )
        for quote in contact.quotes.select_related("prepared_by").order_by("-created_at")[:limit]
    ]
    entries += [
        TimelineEntry(
            when=note.created_at,
            kind="note",
            label="Pinned note" if note.pinned else "Note",
            title=note.body,
            by=_person(note.author),
        )
        for note in contact.note_set.select_related("author").order_by("-created_at")[:limit]
    ]
    messages = (
        Message.objects.filter(ref_contact=contact, channel_id__in=readable_channels(viewer))
        .select_related("channel", "author_user", "author_contact")
        .order_by("-created_at", "-pk")[:limit]
    )
    entries += [
        TimelineEntry(
            when=message.created_at,
            kind="message",
            label=f"Message in {message.channel.name}",
            title=message.body,
            by=_person(message.author_user) or str(message.author_contact or ""),
        )
        for message in messages
    ]
    entries.sort(key=lambda entry: entry.when, reverse=True)
    return entries[:limit]


def upcoming_jobs(contact, limit=10):
    return (
        contact.jobs.filter(scheduled_start__gt=timezone.now(), status=Job.Status.SCHEDULED)
        .select_related("primary_service_type", "service_property")
        .prefetch_related("crew")
        .order_by("scheduled_start", "pk")[:limit]
    )


def with_last_dates(contacts):
    """Annotate last_job_at (latest completed job) and last_touch_at
    (latest Activity) as subqueries — no JOINs, so pagination and other
    annotations stay exact."""
    return contacts.annotate(
        last_job_at=Subquery(
            Job.objects.filter(contact=OuterRef("pk"), status=Job.Status.COMPLETED)
            .order_by("-completed_at")
            .values("completed_at")[:1]
        ),
        last_touch_at=Subquery(
            Activity.objects.filter(contact=OuterRef("pk"))
            .order_by("-created_at")
            .values("created_at")[:1]
        ),
    )
