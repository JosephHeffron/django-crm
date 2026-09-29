from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

# Matches the ten .tone-N classes in static/css/tokens.css — colors are
# classes, not stored hex values, because the production CSP forbids
# inline style attributes.
TONE_VALIDATORS = [MinValueValidator(1), MaxValueValidator(10)]


class UserProfile(models.Model):
    """Per-user details auth.User doesn't carry. Created lazily via
    get_profile() rather than a post_save signal — the same no-signals
    preference as the audit log (docs/DATABASE_DESIGN.md)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    title = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    calendar_tone = models.PositiveSmallIntegerField(default=1, validators=TONE_VALIDATORS)

    def __str__(self):
        return f"Profile for {self.user}"


def get_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile
