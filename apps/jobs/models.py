"""Field-service domain: service catalog, quotes, jobs + crews, photos,
invoicing. Design: docs/DATABASE_DESIGN.md ("Field-service domain
(Phase 17)") and docs/decisions/0009-field-service-domain-model.md.

Line items are *copied* quote → job → invoice, so a later catalog price
change never rewrites a document that was already issued. Totals and
balances are computed (never stored) — see the queryset helpers.
"""

import uuid
from decimal import Decimal
from pathlib import PurePath

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

MONEY = {"max_digits": 12, "decimal_places": 2}
TOTAL_FIELD = DecimalField(max_digits=14, decimal_places=2)
ZERO = Decimal("0.00")
TONE_VALIDATORS = [MinValueValidator(1), MaxValueValidator(10)]


def _sum_subquery(model, fk_name, expression):
    """Σ expression over `model` rows pointing at the outer row, as a
    Subquery — not a JOIN, so annotating several of these on one
    queryset can't multiply rows into each other's sums."""
    return Coalesce(
        Subquery(
            model.objects.filter(**{fk_name: OuterRef("pk")})
            .values(fk_name)
            .annotate(total=Sum(expression))
            .values("total")[:1],
            output_field=TOTAL_FIELD,
        ),
        Value(ZERO),
        output_field=TOTAL_FIELD,
    )


LINE_TOTAL = F("quantity") * F("unit_price")


class ServiceType(models.Model):
    class PricingUnit(models.TextChoices):
        FLAT = "flat", "Flat rate"
        HOUR = "hour", "Per hour"
        WINDOW = "window", "Per window"
        LINEAR_FT = "linear_ft", "Per linear foot"
        SQ_FT = "sq_ft", "Per square foot"
        ITEM = "item", "Per item"

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    default_price = models.DecimalField(**MONEY, default=ZERO, validators=[MinValueValidator(0)])
    pricing_unit = models.CharField(
        max_length=20, choices=PricingUnit.choices, default=PricingUnit.FLAT
    )
    followup_interval_months = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Suggest a follow-up this many months after the last job. "
        "Leave blank to never auto-generate follow-ups for this service.",
    )
    tone = models.PositiveSmallIntegerField(
        default=1, validators=TONE_VALIDATORS, help_text="Calendar color (1-10)."
    )
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self):
        return self.name

    @property
    def tone_class(self):
        return f"tone-{self.tone}"


class LineItem(models.Model):
    service_type = models.ForeignKey(ServiceType, on_delete=models.PROTECT, related_name="+")
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("1"), validators=[MinValueValidator(0)]
    )
    unit_price = models.DecimalField(**MONEY, validators=[MinValueValidator(0)])
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["position", "pk"]

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return self.description or str(self.service_type)


def _line_constraints(prefix):
    return [
        models.CheckConstraint(condition=Q(quantity__gt=0), name=f"{prefix}_quantity_positive"),
        models.CheckConstraint(
            condition=Q(unit_price__gte=0), name=f"{prefix}_unit_price_not_negative"
        ),
    ]


class DocumentQuerySet(models.QuerySet):
    fk_name = None

    def with_totals(self):
        line_model = self.model._meta.get_field("line_items").related_model
        return self.annotate(total_amount=_sum_subquery(line_model, self.fk_name, LINE_TOTAL))


class TotalMixin:
    """`.total` uses the with_totals() annotation when present,
    otherwise one aggregate query."""

    @property
    def total(self):
        if hasattr(self, "total_amount"):
            return self.total_amount
        return self.line_items.aggregate(total=Coalesce(Sum(LINE_TOTAL), Value(ZERO)))["total"]


class QuoteQuerySet(DocumentQuerySet):
    fk_name = "quote"


class Quote(TotalMixin, models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"

    DECIDED_STATUSES = (Status.ACCEPTED, Status.DECLINED, Status.EXPIRED)

    contact = models.ForeignKey("crm.Contact", on_delete=models.PROTECT, related_name="quotes")
    service_property = models.ForeignKey(
        "crm.Property", null=True, blank=True, on_delete=models.SET_NULL, related_name="quotes"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="prepared_quotes"
    )
    site_visit_at = models.DateTimeField(
        null=True, blank=True, help_text="Estimate appointment — shown on the calendar."
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    legacy_deal_id = models.PositiveIntegerField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = QuoteQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["site_visit_at"])]

    def __str__(self):
        return f"{self.number} — {self.contact}"

    @property
    def number(self):
        # Derived from the primary key, not stored: no race to allocate
        # the "next" number, and nothing to keep unique by hand.
        return f"Q-{1000 + self.pk}" if self.pk else "Q-(unsaved)"


class QuoteLineItem(LineItem):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="line_items")

    class Meta(LineItem.Meta):
        constraints = _line_constraints("quote_line")


class JobQuerySet(DocumentQuerySet):
    fk_name = "job"


class Job(TotalMixin, models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    contact = models.ForeignKey("crm.Contact", on_delete=models.PROTECT, related_name="jobs")
    service_property = models.ForeignKey(
        "crm.Property", null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs"
    )
    quote = models.ForeignKey(
        Quote, null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs"
    )
    sales_rep = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sold_jobs",
        help_text="Credited with this job's revenue.",
    )
    primary_service_type = models.ForeignKey(
        ServiceType, on_delete=models.PROTECT, related_name="primary_jobs"
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.SCHEDULED, db_index=True
    )
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    customer_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    crew = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="JobAssignment", related_name="crew_jobs"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_jobs"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = JobQuerySet.as_manager()

    class Meta:
        ordering = ["scheduled_start", "pk"]
        indexes = [models.Index(fields=["scheduled_start"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(scheduled_end__gt=F("scheduled_start")),
                name="job_ends_after_it_starts",
            ),
            models.CheckConstraint(
                condition=Q(customer_rating__isnull=True)
                | Q(customer_rating__gte=1, customer_rating__lte=5),
                name="job_rating_between_1_and_5",
            ),
        ]

    def __str__(self):
        return f"{self.number} — {self.primary_service_type} for {self.contact}"

    @property
    def number(self):
        return f"J-{1000 + self.pk}" if self.pk else "J-(unsaved)"


class JobLineItem(LineItem):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="line_items")

    class Meta(LineItem.Meta):
        constraints = _line_constraints("job_line")


class JobAssignment(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="job_assignments"
    )
    hours_worked = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["job", "user"], name="one_assignment_per_crew_member"),
            models.CheckConstraint(
                condition=Q(hours_worked__isnull=True) | Q(hours_worked__gte=0),
                name="assignment_hours_not_negative",
            ),
        ]

    def __str__(self):
        return f"{self.user} on {self.job.number}"


ALLOWED_PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def photo_upload_to(instance, filename):
    # The stored name is the photo's UUID — never the uploader's own
    # filename (which can leak names/addresses, e.g. "smith_house.jpg").
    # Kept under private/: served only through the login-gated view
    # (Phase 18), never directly by Caddy.
    suffix = PurePath(filename).suffix.lower()
    if suffix not in ALLOWED_PHOTO_SUFFIXES:
        suffix = ".jpg"
    return f"private/photos/{instance.uuid}{suffix}"


class Photo(models.Model):
    class Kind(models.TextChoices):
        BEFORE = "before", "Before"
        AFTER = "after", "After"
        REFERENCE = "reference", "Reference"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    job = models.ForeignKey(
        Job, null=True, blank=True, on_delete=models.CASCADE, related_name="photos"
    )
    quote = models.ForeignKey(
        Quote, null=True, blank=True, on_delete=models.CASCADE, related_name="photos"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.REFERENCE)
    image = models.ImageField(upload_to=photo_upload_to)
    caption = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_photos"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(job__isnull=False) & Q(quote__isnull=True))
                | (Q(job__isnull=True) & Q(quote__isnull=False)),
                name="photo_belongs_to_exactly_one_job_or_quote",
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} photo {self.uuid}"


class InvoiceQuerySet(DocumentQuerySet):
    fk_name = "invoice"

    def with_balances(self):
        return (
            self.with_totals()
            .annotate(paid_amount=_sum_subquery(Payment, "invoice", F("amount")))
            .annotate(balance_amount=F("total_amount") - F("paid_amount"))
        )


class Invoice(TotalMixin, models.Model):
    # Only the states a person sets are stored. "Paid" / "partially
    # paid" / "overdue" are derived from payments and dates
    # (payment_status), so they can never drift out of sync with them.
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        VOID = "void", "Void"

    job = models.ForeignKey(Job, on_delete=models.PROTECT, related_name="invoices")
    contact = models.ForeignKey("crm.Contact", on_delete=models.PROTECT, related_name="invoices")
    issued_on = models.DateField(db_index=True)
    due_on = models.DateField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = InvoiceQuerySet.as_manager()

    class Meta:
        ordering = ["-issued_on", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(due_on__gte=F("issued_on")), name="invoice_due_on_or_after_issue"
            )
        ]

    def __str__(self):
        return f"{self.number} — {self.contact}"

    @property
    def number(self):
        return f"INV-{1000 + self.pk}" if self.pk else "INV-(unsaved)"

    @property
    def paid(self):
        if hasattr(self, "paid_amount"):
            return self.paid_amount
        return self.payments.aggregate(total=Coalesce(Sum("amount"), Value(ZERO)))["total"]

    @property
    def balance(self):
        return self.total - self.paid

    def payment_status(self, today):
        if self.status == self.Status.VOID:
            return "void"
        if self.status == self.Status.DRAFT:
            return "draft"
        balance = self.balance
        if balance <= 0:
            return "paid"
        if self.due_on < today:
            return "overdue"
        return "partially_paid" if self.paid > 0 else "unpaid"


class InvoiceLineItem(LineItem):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="line_items")

    class Meta(LineItem.Meta):
        constraints = _line_constraints("invoice_line")


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CHECK = "check", "Check"
        CARD = "card", "Card"
        TRANSFER = "transfer", "Bank transfer"
        OTHER = "other", "Other"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(**MONEY)
    received_on = models.DateField(db_index=True)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.CARD)
    notes = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_payments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_on", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive")
        ]

    def __str__(self):
        return f"${self.amount} on {self.invoice.number}"


class Expense(models.Model):
    class Category(models.TextChoices):
        SUPPLIES = "supplies", "Supplies & chemicals"
        FUEL = "fuel", "Fuel & vehicle"
        EQUIPMENT = "equipment", "Equipment"
        PAYROLL = "payroll", "Payroll"
        INSURANCE = "insurance", "Insurance"
        MARKETING = "marketing", "Marketing"
        OTHER = "other", "Other"

    date = models.DateField(db_index=True)
    amount = models.DecimalField(**MONEY)
    category = models.CharField(max_length=15, choices=Category.choices)
    description = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_expenses"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="expense_amount_positive")
        ]

    def __str__(self):
        return f"{self.get_category_display()} ${self.amount} on {self.date}"
