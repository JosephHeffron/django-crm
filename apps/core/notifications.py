"""Creating and reading notifications (Phase 17.5 step 4).

Every notification is written here, never by a signal — the same
no-signals preference as the audit log (docs/DATABASE_DESIGN.md), so the
code that causes an event is the code that announces it.

What produces one today:

- a task assigned to someone other than the person assigning it
  (`apps/crm/views.py`);
- a follow-up the generator raises for the person who owns the customer
  (`apps/crm/followups.py`).

Phases 18-20 add the rest as those workflows arrive (an estimate
accepted, a job finished, an invoice paid). Team messages deliberately
don't appear here — the Inbox already carries its own unread count, and
announcing each message twice would just be noise.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Notification

BELL_LIMIT = 8


def notify(recipient, kind, title, body="", url="", event=""):
    """Announce one event to one person. Returns the notification, or
    None when `event` says this person has already been told.

    Nobody is notified about their own action — the caller decides who
    the recipient is, but a recipient of None (an unassigned record) is
    simply skipped.
    """
    if recipient is None:
        return None
    try:
        with transaction.atomic():
            return Notification.objects.create(
                recipient=recipient,
                kind=kind,
                title=title[:160],
                body=body[:300],
                url=url,
                event=event[:120],
            )
    except IntegrityError:
        # The unique (recipient, event) constraint — already announced.
        return None


def unread_notifications(user):
    return Notification.objects.filter(recipient=user, read_at__isnull=True)


def bell(user):
    """What the top bar shows: the newest few, and how many are unread."""
    return {
        "unread": unread_notifications(user).count(),
        "items": list(Notification.objects.filter(recipient=user)[:BELL_LIMIT]),
    }


def mark_all_read(user):
    return unread_notifications(user).update(read_at=timezone.now())


def mark_read(user, pk):
    """Mark one of this person's notifications read. Returns it, or None
    — someone else's row is simply not found, so nothing leaks."""
    notification = Notification.objects.filter(recipient=user, pk=pk).first()
    if notification and notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return notification
