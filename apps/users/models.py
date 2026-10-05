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

    def __str__(self):
        return f"Profile for {self.user}"


def get_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile
