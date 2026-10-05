"""Business-wide records that don't belong to one domain app:

- `BusinessSettings` / `BusinessLink` (Phase 17.5 step 3) — the
  business's own name, logo, contact details, website links, and
  currency, shown in the app shell and, later, on estimates and
  invoices.
- `Notification` / `Goal` (Phase 17.5 step 4) — what the top bar's bell
  lists, and the monthly targets the dashboard measures against.
"""

import uuid

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q


def logo_upload_to(instance, filename):
    # A fresh name per upload (the old file is replaced, and the URL
    # changes so browsers don't keep showing a cached old logo). Always
    # PNG: apps/core/branding.py re-encodes every upload.
    return f"branding/logo-{uuid.uuid4().hex}.png"


class BusinessSettings(models.Model):
    """A single row (pk=1). Read it with BusinessSettings.load()."""

    class Currency(models.TextChoices):
        USD = "USD", "US dollar ($)"
        CAD = "CAD", "Canadian dollar (CA$)"

    SYMBOLS = {Currency.USD: "$", Currency.CAD: "CA$"}

    name = models.CharField(
        "Business name",
        max_length=120,
        blank=True,
        help_text="Leave blank if you're operating as a freelancer",
    )
    logo = models.ImageField(upload_to=logo_upload_to, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "business settings"
        verbose_name_plural = "business settings"
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="single_business_settings_row")
        ]

    def __str__(self):
        return self.display_name

    @classmethod
    def load(cls):
        """The settings row, or unsaved defaults if none has been saved
        yet — reading never writes."""
        return cls.objects.filter(pk=1).first() or cls(pk=1)

    @property
    def display_name(self):
        return self.name or settings.CRM_BRAND_NAME

    @property
    def currency_symbol(self):
        return self.SYMBOLS.get(self.currency, "$")


class BusinessLink(models.Model):
    """A website or social profile shown to customers: one per main
    platform, plus any number of labeled "Other" links."""

    class Platform(models.TextChoices):
        WEBSITE = "website", "Website"
        GOOGLE = "google", "Google Business Profile"
        FACEBOOK = "facebook", "Facebook"
        INSTAGRAM = "instagram", "Instagram"
        YELP = "yelp", "Yelp"
        NEXTDOOR = "nextdoor", "Nextdoor"
        OTHER = "other", "Other"

    platform = models.CharField(max_length=10, choices=Platform.choices)
    label = models.CharField(max_length=60, blank=True, help_text="Required for Other links.")
    url = models.URLField("Link", max_length=300)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform"],
                condition=~Q(platform="other"),
                name="one_link_per_main_platform",
            ),
            models.CheckConstraint(
                condition=~Q(platform="other") | ~Q(label=""), name="other_link_has_label"
            ),
        ]

    def __str__(self):
        return self.display_label

    @property
    def display_label(self):
        return self.label if self.platform == self.Platform.OTHER else self.get_platform_display()


class Notification(models.Model):
    """One thing that happened and the person it matters to — what the
    top bar's bell lists.

    `url` is always a path on this site (a RegexValidator enforces the
    leading slash), because it's rendered straight into an href.

    `event` de-duplicates: the follow-up generator runs every day and is
    idempotent, so without a key per event it would announce the same
    task every morning. A blank key means "no de-duplication" (two
    hand-written notices about the same record are both wanted).
    """

    class Kind(models.TextChoices):
        TASK = "task", "Task"
        FOLLOW_UP = "follow_up", "Follow-up"
        JOB = "job", "Job"
        ESTIMATE = "estimate", "Estimate"
        INVOICE = "invoice", "Invoice"
        SYSTEM = "system", "System"

    # Which accent class the bell list uses for each kind.
    # Matches the icons the sidebar already uses for the same things.
    ICONS = {
        Kind.TASK: "check",
        Kind.FOLLOW_UP: "refresh",
        Kind.JOB: "calendar",
        Kind.ESTIMATE: "briefcase",
        Kind.INVOICE: "dollar",
        Kind.SYSTEM: "info",
    }

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SYSTEM)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=300, blank=True)
    url = models.CharField(
        max_length=300,
        blank=True,
        validators=[RegexValidator(r"^/", "Must be a path on this site.")],
    )
    event = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["recipient", "read_at"], name="notification_inbox_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "event"],
                condition=~Q(event=""),
                name="one_notification_per_event",
            )
        ]

    def __str__(self):
        return self.title

    @property
    def icon(self):
        return self.ICONS.get(self.kind, "info")

    @property
    def is_unread(self):
        return self.read_at is None


class Goal(models.Model):
    """A monthly target the Owner sets; the dashboard measures the
    current calendar month against it (apps/core/goals.py). One row per
    metric — the target in force, not a history of past months."""

    class Metric(models.TextChoices):
        REVENUE = "revenue", "Revenue invoiced"
        JOBS = "jobs", "Jobs completed"
        CUSTOMERS = "customers", "New customers"

    MONEY_METRICS = {Metric.REVENUE}

    metric = models.CharField(max_length=10, choices=Metric.choices, unique=True)
    target = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["metric"]

    def __str__(self):
        return f"{self.get_metric_display()}: {self.target}"

    @property
    def is_money(self):
        return self.metric in self.MONEY_METRICS
