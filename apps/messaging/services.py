from django.db.models import F, Q

from .models import Message


def unread_count(user):
    """Messages in the user's channels after their read marker (all of
    them if they've read nothing yet), not counting their own.

    Both membership conditions sit in one filter() call so they apply
    to the *same* membership row — the user's own, not anyone's.
    """
    return (
        Message.objects.filter(
            Q(channel__memberships__last_read_message__isnull=True)
            | Q(pk__gt=F("channel__memberships__last_read_message")),
            channel__memberships__user=user,
        )
        .exclude(author_user=user)
        .count()
    )
