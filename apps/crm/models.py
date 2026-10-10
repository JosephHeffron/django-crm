from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Concat, Left
from django.urls import reverse
from django.utils import timezone

# How much of an address is remembered when it's placed on the map.
# Long enough for every field at full length, so a pathological
# address can't look permanently stale (apps/crm/models.py Property).
ADDRESS_SNAPSHOT_LENGTH = 450


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


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Contact(models.Model):
    # Lifecycle stage only. Deactivation stays on is_active (existing
    # workflow), so there is no separate "inactive" status to disagree
    # with it (docs/DATABASE_DESIGN.md, Phase 17 section).
    class Status(models.TextChoices):
        LEAD = "lead", "Lead"
        CUSTOMER = "customer", "Customer"

    class LeadSource(models.TextChoices):
        REFERRAL = "referral", "Referral"
        WEBSITE = "website", "Website"
        YARD_SIGN = "yard_sign", "Yard sign"
        DOOR_TO_DOOR = "door_to_door", "Door to door"
        COLD_CALL = "cold_call", "Cold call"
        EVENT = "event", "Event"
        REPEAT = "repeat", "Repeat customer"
        OTHER = "other", "Other"

    class ContactMethod(models.TextChoices):
        CALL = "call", "Call"
        TEXT = "text", "Text"
        EMAIL = "email", "Email"

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.CUSTOMER, db_index=True
    )
    lead_source = models.CharField(max_length=20, choices=LeadSource.choices, blank=True)
    preferred_contact_method = models.CharField(
        max_length=10, choices=ContactMethod.choices, blank=True
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="contacts")
    # Set only by the Phase 17 Lead → Contact data migration, so the
    # fold can be verified and reversed; dropped with Lead in Phase 18.
    legacy_lead_id = models.PositiveIntegerField(null=True, blank=True, editable=False)
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
        return f"{self.first_name} {self.last_name}".strip()

    def get_absolute_url(self):
        return reverse("crm:contact_detail", kwargs={"pk": self.pk})


class Property(models.Model):
    """A service address. A contact can have several (a home plus a
    rental, say); at most one is primary."""

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="properties")
    label = models.CharField(max_length=100, blank=True, help_text="e.g. Home, Rental")
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50)
    postal_code = models.CharField(max_length=20)
    notes = models.TextField(blank=True, help_text="Gate code, dog in yard, access notes…")
    is_primary = models.BooleanField(default=False)
    # Where this address is on the map (Phase 17.5 step 8, ADR 0011).
    # Looked up once through Nominatim, or dropped by hand on the map;
    # `located_at` records when, so an address that changes is looked up
    # again and one that's already placed never is.
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    located_at = models.DateTimeField(null=True, blank=True)
    # The address as it was when it was placed, so an edit re-opens the
    # lookup without having to compare field by field.
    located_address = models.CharField(
        max_length=ADDRESS_SNAPSHOT_LENGTH, blank=True, editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "properties"
        ordering = ["-is_primary", "street"]
        constraints = [
            models.UniqueConstraint(
                fields=["contact"],
                condition=models.Q(is_primary=True),
                name="one_primary_property_per_contact",
            )
        ]

    def __str__(self):
        return f"{self.street}, {self.city}, {self.state} {self.postal_code}"

    @property
    def is_located(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def needs_locating(self):
        """True when nobody has placed this address, or it has been
        edited since it was placed."""
        return not self.is_located or self.located_address != str(self)

    @classmethod
    def needing_location(cls):
        """The same question as `needs_locating`, asked of the database.

        Kept here, beside `__str__`, because it mirrors it: the
        expression has to build the address the same way, and truncate
        it the same way `located_address` is stored, or every address
        would look stale. Asking in SQL rather than in Python is what
        keeps the Map page from loading every property to filter them.
        """
        written = Left(
            Concat(
                "street",
                models.Value(", "),
                "city",
                models.Value(", "),
                "state",
                models.Value(" "),
                "postal_code",
                output_field=models.CharField(),
            ),
            ADDRESS_SNAPSHOT_LENGTH,
        )
        return cls.objects.annotate(current_address=written).filter(
            models.Q(latitude__isnull=True) | ~models.Q(located_address=models.F("current_address"))
        )


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
    class Kind(models.TextChoices):
        GENERAL = "general", "General"
        # Generated when a customer is due for a repeat service
        # (apps/crm/followups.py); completing one logs a contact touch.
        FOLLOW_UP = "follow_up", "Follow-up"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    kind = models.CharField(
        max_length=10, choices=Kind.choices, default=Kind.GENERAL, db_index=True
    )
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
    service_type = models.ForeignKey(
        "jobs.ServiceType",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    quote = models.ForeignKey(
        "jobs.Quote", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    job = models.ForeignKey(
        "jobs.Job", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completed_tasks",
    )
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
        constraints = [
            # A follow-up is always about a specific customer and service.
            models.CheckConstraint(
                condition=~models.Q(kind="follow_up")
                | (models.Q(contact__isnull=False) & models.Q(service_type__isnull=False)),
                name="follow_up_has_contact_and_service",
            ),
            # The generator is idempotent, and this makes it impossible
            # to double up even if two runs overlap.
            models.UniqueConstraint(
                fields=["contact", "service_type"],
                condition=models.Q(kind="follow_up", status="pending"),
                name="one_open_follow_up_per_contact_service",
            ),
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
        indexes = [
            models.Index(fields=["content_type", "object_id", "created_at"]),
            # The index above leads with content_type, so it cannot
            # serve "everything that changed, newest first" — which is
            # what the Change log page asks for (Phase 18.5 unit 5).
            models.Index(fields=["-created_at"], name="crm_audit_recent_idx"),
        ]

    def __str__(self):
        return f"{self.get_action_display()} {self.content_type} #{self.object_id}"


class Activity(models.Model):
    class ActivityType(models.TextChoices):
        CALL = "call", "Call"
        MEETING = "meeting", "Meeting"
        EMAIL = "email", "Email"
        NOTE = "note", "Note"
        TEXT = "text", "Text message"
        VISIT = "visit", "Site visit"
        # Logged automatically when a follow-up task is completed —
        # resets that contact's follow-up clock.
        FOLLOW_UP = "follow_up", "Follow-up"

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


class Note(models.Model):
    """A free-form note — general (no links) or about a contact or job."""

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="notes"
    )
    body = models.TextField()
    contact = models.ForeignKey(
        Contact, null=True, blank=True, on_delete=models.CASCADE, related_name="note_set"
    )
    job = models.ForeignKey(
        "jobs.Job", null=True, blank=True, on_delete=models.CASCADE, related_name="note_set"
    )
    pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pinned", "-created_at"]

    def __str__(self):
        return self.body[:60]


class BusinessPlan(models.Model):
    """A goal or initiative (e.g. "Launch gutter-guard upsell"), with an
    owner, a due date, and a checklist."""

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        ON_HOLD = "on_hold", "On hold"
        DONE = "done", "Done"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="business_plans"
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.NOT_STARTED, db_index=True
    )
    priority = models.CharField(
        max_length=10, choices=Task.Priority.choices, default=Task.Priority.MEDIUM
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_business_plans"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "pk"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("crm:plan_detail", kwargs={"pk": self.pk})


class PlanChecklistItem(models.Model):
    plan = models.ForeignKey(BusinessPlan, on_delete=models.CASCADE, related_name="items")
    text = models.CharField(max_length=255)
    is_done = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return self.text
