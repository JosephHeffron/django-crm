"""Business-wide settings (Phase 17.5 step 3): the business's own name,
logo, contact details, website links, and currency — shown in the app
shell and, later, on estimates and invoices."""

import uuid

from django.conf import settings
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
