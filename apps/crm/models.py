from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Company(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="owned_companies",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_companies",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "companies"
        ordering = ["name"]
        indexes = [models.Index(fields=["owner"])]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("crm:company_detail", kwargs={"pk": self.pk})


class Contact(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField(max_length=30, blank=True)
    title = models.CharField(max_length=150, blank=True)
    company = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contacts",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="owned_contacts",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_contacts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["owner"]),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_absolute_url(self):
        return reverse("crm:contact_detail", kwargs={"pk": self.pk})


class Lead(models.Model):
    class Source(models.TextChoices):
        WEBSITE = "website", "Website"
        REFERRAL = "referral", "Referral"
        COLD_CALL = "cold_call", "Cold call"
        EVENT = "event", "Event"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        QUALIFIED = "qualified", "Qualified"
        UNQUALIFIED = "unqualified", "Unqualified"
        CONVERTED = "converted", "Converted"

    name = models.CharField(max_length=200)
    company_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.OTHER)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW, db_index=True
    )
    notes = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="owned_leads",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_leads",
    )
    converted_at = models.DateTimeField(null=True, blank=True)
    converted_company = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="converted_from_leads",
    )
    converted_contact = models.ForeignKey(
        Contact,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="converted_from_leads",
    )
    converted_deal = models.ForeignKey(
        "Deal",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="converted_from_leads",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["owner"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("crm:lead_detail", kwargs={"pk": self.pk})


class Deal(models.Model):
    class Stage(models.TextChoices):
        PROSPECTING = "prospecting", "Prospecting"
        QUALIFICATION = "qualification", "Qualification"
        PROPOSAL = "proposal", "Proposal"
        NEGOTIATION = "negotiation", "Negotiation"
        CLOSED_WON = "closed_won", "Closed won"
        CLOSED_LOST = "closed_lost", "Closed lost"

    CLOSED_STAGES = (Stage.CLOSED_WON, Stage.CLOSED_LOST)

    title = models.CharField(max_length=255)
    company = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="deals",
    )
    contact = models.ForeignKey(
        Contact,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="deals",
    )
    value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stage = models.CharField(
        max_length=20, choices=Stage.choices, default=Stage.PROSPECTING, db_index=True
    )
    probability = models.PositiveSmallIntegerField(null=True, blank=True)
    expected_close_date = models.DateField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="owned_deals",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_deals",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(company__isnull=False) | models.Q(contact__isnull=False),
                name="deal_has_company_or_contact",
            ),
            models.CheckConstraint(
                condition=models.Q(probability__isnull=True)
                | (models.Q(probability__gte=0) & models.Q(probability__lte=100)),
                name="deal_probability_between_0_and_100",
            ),
        ]
        indexes = [
            models.Index(fields=["stage"]),
            models.Index(fields=["owner"]),
            models.Index(fields=["expected_close_date"]),
        ]

    @property
    def is_open(self):
        return self.stage not in self.CLOSED_STAGES

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("crm:deal_detail", kwargs={"pk": self.pk})


class Task(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_tasks",
    )
    contact = models.ForeignKey(
        Contact,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    deal = models.ForeignKey(
        Deal,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
            models.Index(fields=["assigned_to"]),
        ]

    @property
    def is_overdue(self):
        return (
            self.status == self.Status.PENDING
            and self.due_date is not None
            and self.due_date < timezone.localdate()
        )

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("crm:task_detail", kwargs={"pk": self.pk})


class AuditLogEntry(models.Model):
    """Who changed a Company/Contact/Lead/Deal, what changed, and when.

    Deliberately lightweight — no reconstruction of past states, no
    revert, no event-sourcing (docs/DATABASE_DESIGN.md's "Audit history"
    section). Only Company/Contact/Lead/Deal are ever pointed at here;
    Task and Activity are out of scope (see that section for why).
    """

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"

    content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    record = GenericForeignKey("content_type", "object_id")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_log_entries",
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "audit log entries"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["content_type", "object_id", "created_at"])]

    def __str__(self):
        return f"{self.get_action_display()} {self.content_type} #{self.object_id}"


class Activity(models.Model):
    class ActivityType(models.TextChoices):
        CALL = "call", "Call"
        MEETING = "meeting", "Meeting"
        EMAIL = "email", "Email"
        NOTE = "note", "Note"

    activity_type = models.CharField(max_length=10, choices=ActivityType.choices, db_index=True)
    subject = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    company = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
    )
    contact = models.ForeignKey(
        Contact,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
    )
    lead = models.ForeignKey(
        Lead,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
    )
    deal = models.ForeignKey(
        Deal,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_activities",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name_plural = "activities"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["activity_type"])]

    def __str__(self):
        return self.subject

    def save(self, *args, **kwargs):
        # Activity is documented as immutable history
        # (docs/DATABASE_DESIGN.md). Enforced here — not just in
        # ActivityAdmin.has_change_permission — because a plain
        # .save() on an existing instance previously bypassed that
        # entirely (docs/DATABASE_REVIEW.md finding #7, confirmed
        # empirically). Bulk .update()/.bulk_update() calls still
        # bypass this, same as any Django model — documented as an
        # accepted, narrower residual gap.
        if self.pk is not None:
            raise ValueError("Activity records are immutable and cannot be updated after creation.")
        super().save(*args, **kwargs)
