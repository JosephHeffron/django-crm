from django import forms

from .models import ServiceType

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


class ServiceTypeForm(forms.ModelForm):
    tone = forms.TypedChoiceField(
        choices=TONE_CHOICES, coerce=int, label="Calendar color", help_text=None
    )

    class Meta:
        model = ServiceType
        fields = [
            "name",
            "description",
            "default_price",
            "pricing_unit",
            "followup_interval_months",
            "tone",
            "is_active",
        ]
        labels = {
            "followup_interval_months": "Follow-up interval (months)",
            "is_active": "Offered",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
