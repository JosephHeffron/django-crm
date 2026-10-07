from django import forms
from django.db.models import Q

from .models import Activity, Company, Contact, Deal, Lead, Task


class ContactChoiceField(forms.ModelChoiceField):
    """A customer picker that reads in the order it's sorted.

    Contact sorts by surname (`Contact.Meta.ordering`) but `__str__`
    renders "Daniel Adams", so a plain dropdown looked unsorted to
    anyone reading the first names — Daniel, Michelle, Andrew, Betty.
    Surname first means the visible text and the sort agree.
    """

    def label_from_instance(self, obj):
        both = f"{obj.last_name}, {obj.first_name}".strip(", ")
        return both or str(obj) or f"Customer {obj.pk}"


def contact_choices(chosen=None):
    """Active customers, surname order.

    `chosen` is kept whatever its state, so editing a record that names
    a deactivated customer still shows them instead of silently
    dropping the field's own value. Same escape hatch the line formsets
    use for retired services.
    """
    condition = Q(is_active=True)
    if chosen:
        condition |= Q(pk=chosen)
    return Contact.objects.filter(condition).order_by("last_name", "first_name", "pk")


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
            "status",
            "email",
            "phone",
            "preferred_contact_method",
            "lead_source",
            "tags",
            "title",
            "company",
            "notes",
            "is_active",
            "owner",
        ]
        labels = {"status": "Stage"}
        widgets = {"tags": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional so posts that predate the field keep working: a
        # missing stage keeps the contact's current one (Customer for a
        # new contact, the model default).
        self.fields["status"].required = False

    def clean_status(self):
        return self.cleaned_data.get("status") or self.instance.status


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


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "assigned_to",
            "contact",
            "quote",
            "due_date",
            "priority",
            "status",
        ]
        labels = {"contact": "Customer", "quote": "Estimate"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Was `deal`, which has been empty since Phase 17 folded every
        # Deal into a Quote — the dropdown rendered with nothing in it.
        # Task.quote already exists and the fold migration populated it.
        self.fields["contact"] = ContactChoiceField(
            queryset=contact_choices(self.instance.contact_id),
            # Task.contact is null=True/blank=True: a general to-do
            # needn't name anyone. clean_contact() still insists for a
            # follow-up, which the database also checks.
            required=False,
            label="Customer",
        )
        self.fields["quote"].queryset = (
            self.fields["quote"].queryset.select_related("contact").order_by("-pk")
        )

    def clean_contact(self):
        # A follow-up must name its customer (DB check
        # follow_up_has_contact_and_service); catch that here as a form
        # error instead of letting the save fail with a 500.
        contact = self.cleaned_data.get("contact")
        if self.instance.kind == Task.Kind.FOLLOW_UP and contact is None:
            raise forms.ValidationError("A follow-up needs its customer.")
        return contact
