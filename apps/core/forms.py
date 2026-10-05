from django import forms
from django.forms import BaseModelFormSet, modelformset_factory

from .models import BusinessLink, BusinessSettings, Goal


class BusinessSettingsForm(forms.ModelForm):
    class Meta:
        model = BusinessSettings
        fields = ["name", "contact_email", "contact_phone", "currency"]
        labels = {"contact_email": "Contact Email", "contact_phone": "Contact Phone"}


class LogoForm(forms.Form):
    """The logo file plus the square the crop tool chose (in the original
    image's pixels; blank = the center square)."""

    logo_file = forms.FileField(required=False, label="Company Logo")
    # Kept as text: anything the page script didn't write falls back to
    # the center square (what happens without JavaScript anyway) rather
    # than failing validation on a hidden field nobody can see or fix.
    crop_x = forms.CharField(required=False, widget=forms.HiddenInput)
    crop_y = forms.CharField(required=False, widget=forms.HiddenInput)
    crop_size = forms.CharField(required=False, widget=forms.HiddenInput)
    remove_logo = forms.BooleanField(required=False, label="Remove the current logo")

    def crop(self):
        try:
            return tuple(int(self.cleaned_data[k]) for k in ("crop_x", "crop_y", "crop_size"))
        except (KeyError, TypeError, ValueError):
            return None


class BaseLinkFormSet(BaseModelFormSet):
    def clean(self):
        super().clean()
        seen = set()
        for form in self.forms:
            if not getattr(form, "cleaned_data", None) or form.cleaned_data.get("DELETE"):
                continue
            platform = form.cleaned_data.get("platform")
            if not platform:
                continue
            if platform == BusinessLink.Platform.OTHER:
                if not form.cleaned_data.get("label"):
                    form.add_error("label", "Give this link a label.")
            elif platform in seen:
                form.add_error("platform", "Only one link per platform — use Other for more.")
            seen.add(platform)


LinkFormSet = modelformset_factory(
    BusinessLink,
    formset=BaseLinkFormSet,
    fields=["platform", "label", "url"],
    # One blank row is always offered, so adding a link works without
    # JavaScript; the page script adds more on demand. Blank rows are
    # ignored on save.
    extra=1,
    can_delete=True,
)


class GoalsForm(forms.Form):
    """The Owner's monthly targets (Phase 17.5 step 4). A blank field
    means "no target for this" — the row is removed and the dashboard
    stops measuring it, rather than measuring against zero."""

    revenue = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        label="Revenue invoiced",
        help_text="Invoiced in the calendar month.",
    )
    jobs = forms.IntegerField(
        required=False,
        min_value=0,
        label="Jobs completed",
        help_text="Jobs marked complete in the month.",
    )
    customers = forms.IntegerField(
        required=False,
        min_value=0,
        label="New customers",
        help_text="Customers added in the month.",
    )

    def __init__(self, *args, **kwargs):
        # Counts come back as whole numbers; only money keeps its cents.
        kwargs.setdefault(
            "initial",
            {
                goal.metric: goal.target if goal.is_money else int(goal.target)
                for goal in Goal.objects.all()
            },
        )
        super().__init__(*args, **kwargs)

    def save(self):
        for metric in Goal.Metric.values:
            target = self.cleaned_data.get(metric)
            if target is None:
                Goal.objects.filter(metric=metric).delete()
            else:
                Goal.objects.update_or_create(metric=metric, defaults={"target": target})
