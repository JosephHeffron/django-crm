from django import forms
from django.contrib.auth import get_user_model

from .models import UserProfile

TONE_CHOICES = [
    (1, "Blue"),
    (2, "Green"),
    (3, "Yellow"),
    (4, "Red"),
    (5, "Purple"),
    (6, "Teal"),
    (7, "Orange"),
    (8, "Pink"),
    (9, "Gray"),
    (10, "Olive"),
]


class AccountForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email"]


class ProfileForm(forms.ModelForm):
    calendar_tone = forms.TypedChoiceField(choices=TONE_CHOICES, coerce=int, label="Your color")

    class Meta:
        model = UserProfile
        fields = ["title", "phone", "calendar_tone"]


class CrewPayForm(forms.ModelForm):
    """What the Owner sets for someone else: their hourly rate and the
    days they normally work (Phase 17.5 step 7). Nobody sets their own —
    that's the Owner's call."""

    working_days = forms.MultipleChoiceField(
        choices=UserProfile.WEEKDAYS,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Normally works",
        help_text="Used to flag a job booked on someone's day off. Leave "
        "every box clear if their days vary.",
    )

    class Meta:
        model = UserProfile
        fields = ["hourly_rate"]
        labels = {"hourly_rate": "Hourly rate"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["working_days"].initial = sorted(self.instance.working_day_numbers)

    def clean_working_days(self):
        return "".join(sorted(self.cleaned_data["working_days"]))

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.working_days = self.cleaned_data["working_days"]
        if commit:
            profile.save()
        return profile
