"""Internal team messaging, shaped so customer SMS can be added later
without a schema rewrite (docs/decisions/0009-field-service-domain-model.md):

- Channel.kind already reserves ``customer_sms`` (with Channel.contact).
- Message can be authored by a user *or* a contact (an inbound text).
- Message.transport / direction / external_id / delivery_status carry
  what an SMS provider (e.g. Twilio) reports, unused for internal chat.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q


class Channel(models.Model):
    class Kind(models.TextChoices):
        PUBLIC = "public", "Channel"
        DIRECT = "direct", "Direct message"
        # Reserved for Phase 24 (customer texting); not used yet.
        CUSTOMER_SMS = "customer_sms", "Customer SMS"

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    kind = models.CharField(max_length=15, choices=Kind.choices, default=Kind.PUBLIC)
    topic = models.CharField(max_length=255, blank=True)
    # PROTECT, not SET_NULL: an SMS channel must name its contact (DB
    # check below), so nulling it could never succeed anyway — PROTECT
    # says so directly instead of failing on the check constraint.
    contact = models.ForeignKey(
        "crm.Contact",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sms_channels",
    )
    is_archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_channels",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(kind="customer_sms") | Q(contact__isnull=False),
                name="sms_channel_has_contact",
            )
        ]

    def __str__(self):
        return f"#{self.name}" if self.kind == self.Kind.PUBLIC else self.name


class Message(models.Model):
    class Transport(models.TextChoices):
        INTERNAL = "internal", "Internal"
        SMS = "sms", "SMS"

    class Direction(models.TextChoices):
        INTERNAL = "internal", "Internal"
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="messages")
    author_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="messages",
    )
    author_contact = models.ForeignKey(
        "crm.Contact",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="messages_authored",
    )
    body = models.TextField()
    transport = models.CharField(
        max_length=10, choices=Transport.choices, default=Transport.INTERNAL
    )
    direction = models.CharField(
        max_length=10, choices=Direction.choices, default=Direction.INTERNAL
    )
    external_id = models.CharField(max_length=100, blank=True)
    delivery_status = models.CharField(max_length=30, blank=True)
    # A message can point at the job, contact, or quote it's about.
    ref_job = models.ForeignKey(
        "jobs.Job", null=True, blank=True, on_delete=models.SET_NULL, related_name="messages"
    )
    ref_contact = models.ForeignKey(
        "crm.Contact",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referencing_messages",
    )
    ref_quote = models.ForeignKey(
        "jobs.Quote", null=True, blank=True, on_delete=models.SET_NULL, related_name="messages"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["channel", "id"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(author_user__isnull=False) | Q(author_contact__isnull=False),
                name="message_has_an_author",
            )
        ]

    def __str__(self):
        return self.body[:60]


class ChannelMembership(models.Model):
    """Who's in a channel, and how far they've read — unread count is
    the number of messages after last_read_message."""

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="channel_memberships"
    )
    last_read_message = models.ForeignKey(
        Message, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["channel", "user"], name="one_membership_per_channel")
        ]

    def __str__(self):
        return f"{self.user} in {self.channel}"
