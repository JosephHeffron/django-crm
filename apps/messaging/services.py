"""Who can read which channel, unread counts, read markers, and direct
messages (Phase 17 unit 3d).

A public channel is readable by the roles in its ``audience``; a direct
channel only by its members. Everything that shows or counts messages
goes through visible_channels(), so a Cleaner never sees #sales (not in
the list, not in the unread badge, 404 by URL).
"""

from django.db import IntegrityError, transaction
from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.users.roles import SALES_ROLES, user_role

from .models import Channel, ChannelMembership, Message

DM_SLUG_PREFIX = "dm-"


def visible_channels(user):
    role = user_role(user)
    if role is None:
        return Channel.objects.none()
    audiences = [Channel.Audience.EVERYONE]
    if role in SALES_ROLES:
        audiences.append(Channel.Audience.SALES)
    return Channel.objects.filter(is_archived=False).filter(
        Q(kind=Channel.Kind.PUBLIC, audience__in=audiences)
        | Q(
            kind=Channel.Kind.DIRECT,
            pk__in=ChannelMembership.objects.filter(user=user).values("channel_id"),
        )
    )


def unread_count(user):
    """Total unread across the channels the user can read — the same
    per-channel figure the Messages page shows (channels_for), so the
    badge and the list always agree."""
    return channels_for(user).aggregate(total=Sum("unread"))["total"] or 0


def channels_for(user):
    """visible_channels() annotated with ``unread`` (per the user's own
    read marker; a channel they haven't opened counts everything) and
    ``last_message_at``, busiest-recent first."""
    last_read = Coalesce(
        Subquery(
            ChannelMembership.objects.filter(channel=OuterRef("pk"), user=user).values(
                "last_read_message_id"
            )[:1]
        ),
        Value(0),
        output_field=IntegerField(),
    )
    unread = Coalesce(
        Subquery(
            Message.objects.filter(channel=OuterRef("pk"), pk__gt=OuterRef("last_read"))
            .exclude(author_user=user)
            .values("channel")
            .annotate(n=Count("pk"))
            .values("n")[:1]
        ),
        Value(0),
    )
    latest = Subquery(
        Message.objects.filter(channel=OuterRef("pk")).order_by("-pk").values("created_at")[:1]
    )
    return (
        visible_channels(user)
        .annotate(last_read=last_read)
        .annotate(unread=unread, last_message_at=latest)
        .prefetch_related("memberships__user")
        .order_by(F("last_message_at").desc(nulls_last=True), "name")
    )


def mark_read(channel, user):
    """Move the user's read marker to the channel's newest message —
    forward only, so an old tab can't un-read newer messages."""
    newest = channel.messages.order_by("-pk").values_list("pk", flat=True).first()
    membership, _ = ChannelMembership.objects.get_or_create(channel=channel, user=user)
    if newest and (membership.last_read_message_id or 0) < newest:
        membership.last_read_message_id = newest
        membership.save(update_fields=["last_read_message"])


def direct_channel(user, other):
    """The one direct channel between two users, created on first use."""
    low, high = sorted((user.pk, other.pk))
    slug = f"{DM_SLUG_PREFIX}{low}-{high}"
    try:
        with transaction.atomic():
            channel, _ = Channel.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": "Direct message",
                    "kind": Channel.Kind.DIRECT,
                    "created_by": user,
                },
            )
    except IntegrityError:  # created by the other person at the same moment
        channel = Channel.objects.get(slug=slug)
    for member in (user, other):
        ChannelMembership.objects.get_or_create(channel=channel, user=member)
    return channel


def channel_title(channel, viewer):
    """#name for a public channel; the other person's name for a DM."""
    if channel.kind == Channel.Kind.PUBLIC:
        return f"#{channel.name}"
    others = [
        m.user.get_full_name() or m.user.get_username()
        for m in channel.memberships.all()
        if m.user_id != viewer.pk
    ]
    return ", ".join(others) or channel.name
