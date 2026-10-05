import uuid
from pathlib import PurePath

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

# Matches the ten .tone-N classes in static/css/tokens.css — colors are
# classes, not stored hex values, because the production CSP forbids
# inline style attributes.
TONE_VALIDATORS = [MinValueValidator(1), MaxValueValidator(10)]


def avatar_upload_to(instance, filename):
    # Random name, never the uploaded filename (same reasoning as job
    # photos in apps/jobs/models.py).
    suffix = PurePath(filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    return f"private/avatars/{uuid.uuid4().hex}{suffix}"


class UserProfile(models.Model):
    """Per-user details auth.User doesn't carry. Created lazily via
    get_profile() rather than a post_save signal — the same no-signals
    preference as the audit log (docs/DATABASE_DESIGN.md)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    title = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    # Under media/private/ — served only through a login-gated view
    # (Phase 18), never directly by Caddy.
    photo = models.ImageField(upload_to=avatar_upload_to, blank=True)
    calendar_tone = models.PositiveSmallIntegerField(default=1, validators=TONE_VALIDATORS)

    class Theme(models.TextChoices):
        SYSTEM = "system", "Match my device"
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    # Saved on the profile so it follows the person across devices, and
    # applied server-side as <html data-theme> (no flash of the wrong
    # theme, no browser storage) — docs/decisions/0010.
    theme = models.CharField(max_length=10, choices=Theme.choices, default=Theme.SYSTEM)

    # The dashboard's setup checklist hides itself once every step is
    # done; this is the "hide it anyway" choice (apps/core/onboarding.py).
    onboarding_dismissed = models.BooleanField(default=False)

    # Crew pay and availability (Phase 17.5 step 7). The Owner sets
    # both; nobody else sees another person's rate.
    hourly_rate = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="What this person is paid per hour. Payroll needs it.",
    )
    # The weekdays they normally work, as digits (Monday is 0): "01234"
    # is a weekday crew. Stored as text rather than seven booleans so
    # adding a day is editing a string, not a migration.
    working_days = models.CharField(max_length=7, blank=True)

    WEEKDAYS = (
        (0, "Mon"),
        (1, "Tue"),
        (2, "Wed"),
        (3, "Thu"),
        (4, "Fri"),
        (5, "Sat"),
        (6, "Sun"),
    )

    @property
    def working_day_numbers(self):
        return {int(day) for day in self.working_days if day.isdigit()}

    @property
    def working_days_display(self):
        days = self.working_day_numbers
        if not days:
            return ""
        return ", ".join(label for number, label in self.WEEKDAYS if number in days)

    def works_on(self, day):
        """Whether this person normally works that date. With no days
        set we don't know, so we don't claim they don't."""
        return not self.working_days or day.weekday() in self.working_day_numbers

    def __str__(self):
        return f"Profile for {self.user}"


def get_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile
