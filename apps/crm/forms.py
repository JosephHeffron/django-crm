from django import forms

from .models import Activity, Company, Contact, Deal, Lead


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            "name",
            "website",
            "phone",
            "industry",
            "notes",
            "is_active",
            "owner",
        ]


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "title",
            "company",
            "notes",
            "is_active",
            "owner",
        ]


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            "name",
            "company_name",
            "email",
            "phone",
            "source",
            "status",
            "notes",
            "owner",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Converting happens through the dedicated conversion workflow
        # (LeadConvertView), not by picking "Converted" here — that's
        # what keeps converted_at/converted_company/converted_contact/
        # converted_deal consistent with the status change.
        self.fields["status"].choices = [
            choice for choice in Lead.Status.choices if choice[0] != Lead.Status.CONVERTED
        ]
        if self.instance.pk and self.instance.status == Lead.Status.CONVERTED:
            self.fields["status"].disabled = True


class LeadConversionForm(forms.Form):
    existing_company = forms.ModelChoiceField(
        queryset=Company.objects.order_by("name"),
        required=False,
        label="Link to an existing company",
    )
    new_company_name = forms.CharField(required=False, label="Or create a new company named")
    contact_first_name = forms.CharField(label="Contact first name")
    contact_last_name = forms.CharField(label="Contact last name")
    contact_email = forms.EmailField(required=False, label="Contact email")
    contact_phone = forms.CharField(required=False, max_length=30, label="Contact phone")
    create_deal = forms.BooleanField(required=False, initial=True, label="Also open a deal")
    deal_title = forms.CharField(required=False, label="Deal title")
    deal_value = forms.DecimalField(
        required=False, max_digits=12, decimal_places=2, label="Deal value"
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("existing_company") and cleaned_data.get("new_company_name"):
            raise forms.ValidationError("Choose an existing company or name a new one, not both.")
        if cleaned_data.get("create_deal") and not cleaned_data.get("deal_title"):
            self.add_error("deal_title", "A deal needs a title.")
        return cleaned_data


class DealForm(forms.ModelForm):
    class Meta:
        model = Deal
        fields = [
            "title",
            "company",
            "contact",
            "value",
            "stage",
            "probability",
            "expected_close_date",
            "notes",
            "owner",
        ]

    def clean(self):
        # Mirrors Deal's own DB-level CheckConstraints
        # (docs/DATABASE_DESIGN.md) at the form layer, so bad input gets
        # a normal field error here instead of an IntegrityError/500 —
        # a lesson carried over from Companies/Contacts CRUD, applied
        # proactively rather than found by review this time.
        cleaned_data = super().clean()
        if not cleaned_data.get("company") and not cleaned_data.get("contact"):
            raise forms.ValidationError("A deal needs a company, a contact, or both.")

        probability = cleaned_data.get("probability")
        if probability is not None and not (0 <= probability <= 100):
            self.add_error("probability", "Probability must be between 0 and 100.")
        return cleaned_data


class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = [
            "activity_type",
            "subject",
            "description",
            "company",
            "contact",
            "lead",
            "deal",
        ]

    def clean(self):
        # The DB-level "at least one relation" constraint was removed
        # (docs/DATABASE_REVIEW.md finding #2 — an Activity may
        # legitimately degrade to zero relations if the things it once
        # referenced get deleted), but a *new* Activity should still be
        # tagged to at least one record on creation. Enforced here, at
        # the form layer, per docs/DATABASE_DESIGN.md's plan for this.
        cleaned_data = super().clean()
        if not any(cleaned_data.get(field) for field in ("company", "contact", "lead", "deal")):
            raise forms.ValidationError(
                "An activity needs to be linked to a company, contact, lead, or deal."
            )
        return cleaned_data
