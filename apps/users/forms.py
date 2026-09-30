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
