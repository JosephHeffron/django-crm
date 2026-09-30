from django import forms

from apps.users.forms import TONE_CHOICES

from .models import ServiceType


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
