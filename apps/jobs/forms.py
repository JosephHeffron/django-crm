from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.crm.forms import ContactChoiceField, contact_choices
from apps.crm.models import Property
from apps.users.forms import TONE_CHOICES
from apps.users.roles import Role

from .models import (
    Expense,
    Invoice,
    InvoiceLineItem,
    Job,
    JobLineItem,
    Payment,
    Quote,
    QuoteLineItem,
    ServiceType,
)


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


# A browser's datetime-local input sends "2026-10-07T09:00"; Django's
# default input formats don't include the "T", so say so explicitly.
DATETIME_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]
DATETIME_WIDGET = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class ServiceSelect(forms.Select):
    """A service picker that carries each service's default price on its
    own option, so the page script can fill a blank price without a
    second request — and without an inline script, which the CSP
    forbids."""

    def create_option(self, name, value, *args, **kwargs):
        option = super().create_option(name, value, *args, **kwargs)
        price = getattr(getattr(value, "instance", None), "default_price", None)
        if price is not None:
            option["attrs"]["data-price"] = f"{price}"
        return option


def person(user):
    return user.get_full_name() or user.get_username()


class PeopleChoiceField(forms.ModelChoiceField):
    """People by name, not by username — "Casey Brooks", not
    "demo_casey"."""

    def label_from_instance(self, obj):
        return person(obj)


class PeopleMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return person(obj)


class PropertyChoiceField(forms.ModelChoiceField):
    """Addresses carry the customer's name: the list holds every
    customer's addresses, and "12 Oak Ave" alone doesn't say whose."""

    def label_from_instance(self, obj):
        return f"{obj.contact} — {obj}"


def crew_queryset():
    return (
        get_user_model()
        .objects.filter(is_active=True, groups__name=Role.CLEANER.value)
        .order_by("first_name", "last_name", "username")
    )


class JobForm(forms.ModelForm):
    """Book a job, or move one (Phase 17.5 step 5).

    The address list isn't narrowed to the chosen customer in the markup
    — that would need JavaScript, and the page works without it — so
    `clean()` refuses an address belonging to somebody else rather than
    silently filing the job at the wrong house.
    """

    scheduled_start = forms.DateTimeField(
        label="Starts", input_formats=DATETIME_FORMATS, widget=DATETIME_WIDGET
    )
    scheduled_end = forms.DateTimeField(
        label="Ends", input_formats=DATETIME_FORMATS, widget=DATETIME_WIDGET
    )
    crew = PeopleMultipleChoiceField(
        queryset=get_user_model().objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Crew",
        help_text="Who's doing the work. They'll see the job on their own schedule.",
    )

    class Meta:
        model = Job
        fields = [
            "contact",
            "service_property",
            "primary_service_type",
            "status",
            "scheduled_start",
            "scheduled_end",
            "sales_rep",
            "notes",
        ]
        labels = {
            "contact": "Customer",
            "service_property": "Address",
            "primary_service_type": "Service",
            "sales_rep": "Sold by",
        }
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["crew"].queryset = crew_queryset()
        self.fields["contact"] = ContactChoiceField(
            queryset=contact_choices(self.instance.contact_id), label="Customer"
        )
        self.fields["primary_service_type"].queryset = ServiceType.objects.filter(is_active=True)
        self.fields["service_property"] = PropertyChoiceField(
            queryset=Property.objects.select_related("contact"),
            required=False,
            label="Address",
        )
        sellers = [Role.OWNER.value, Role.SALES_REP.value]
        self.fields["sales_rep"] = PeopleChoiceField(
            queryset=get_user_model()
            .objects.filter(is_active=True, groups__name__in=sellers)
            .distinct()
            .order_by("first_name", "last_name", "username"),
            required=False,
            label="Sold by",
            help_text=Job._meta.get_field("sales_rep").help_text,
        )
        if self.instance.pk:
            self.fields["crew"].initial = self.instance.crew.all()

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("scheduled_start"), cleaned.get("scheduled_end")
        if start and end and end <= start:
            self.add_error("scheduled_end", "The end time has to be after the start time.")
        contact, service_property = cleaned.get("contact"), cleaned.get("service_property")
        if contact and service_property and service_property.contact_id != contact.pk:
            self.add_error("service_property", "That address belongs to a different customer.")
        return cleaned


class BaseLineFormSet(forms.BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        # Only services you still offer — plus whichever one this line
        # already names, so retiring a service doesn't make every old
        # job impossible to edit.
        chosen = getattr(form.instance, "service_type_id", None)
        condition = Q(is_active=True) | Q(pk=chosen) if chosen else Q(is_active=True)
        form.fields["service_type"].queryset = ServiceType.objects.filter(condition)

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        kept = [
            form
            for form in self.forms
            if form.cleaned_data
            and not form.cleaned_data.get("DELETE")
            and form.cleaned_data.get("service_type")
        ]
        for position, form in enumerate(kept):
            form.instance.position = position


LINE_FIELDS = ["service_type", "description", "quantity", "unit_price"]


def line_formset(parent, line_model, extra=1):
    """The same editable list of work for a job, an estimate, and an
    invoice.

    `extra` is how many blank rows are offered. A formset renders
    exactly that many no matter how many initial rows it's handed, so a
    caller seeding it with existing lines has to size it to them —
    otherwise the rest are silently dropped.
    """
    return forms.inlineformset_factory(
        parent,
        line_model,
        formset=BaseLineFormSet,
        fields=LINE_FIELDS,
        widgets={"service_type": ServiceSelect},
        extra=extra,
        can_delete=True,
    )


JobLineFormSet = line_formset(Job, JobLineItem)
QuoteLineFormSet = line_formset(Quote, QuoteLineItem)


class QuoteForm(forms.ModelForm):
    """Write an estimate (Phase 17.5 step 5). Same address check as
    JobForm, for the same reason."""

    site_visit_at = forms.DateTimeField(
        label="Site visit",
        required=False,
        input_formats=DATETIME_FORMATS,
        widget=DATETIME_WIDGET,
        help_text="When you're going to look at the work. It shows on the schedule.",
    )

    class Meta:
        model = Quote
        fields = [
            "contact",
            "service_property",
            "status",
            "site_visit_at",
            "expires_on",
            "notes",
        ]
        labels = {
            "contact": "Customer",
            "service_property": "Address",
            "expires_on": "Good until",
        }
        widgets = {
            "expires_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contact"] = ContactChoiceField(
            queryset=contact_choices(self.instance.contact_id), label="Customer"
        )
        self.fields["service_property"] = PropertyChoiceField(
            queryset=Property.objects.select_related("contact"),
            required=False,
            label="Address",
        )

    def clean(self):
        cleaned = super().clean()
        contact, service_property = cleaned.get("contact"), cleaned.get("service_property")
        if contact and service_property and service_property.contact_id != contact.pk:
            self.add_error("service_property", "That address belongs to a different customer.")
        return cleaned


class InvoiceForm(forms.ModelForm):
    """Bill a job. The customer isn't asked for — it's the job's
    customer, and two fields that must agree are two fields that can
    disagree."""

    class Meta:
        model = Invoice
        fields = ["job", "issued_on", "due_on", "status", "notes"]
        labels = {"issued_on": "Issued", "due_on": "Due"}
        widgets = {
            "issued_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "due_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["job"].queryset = Job.objects.select_related(
            "contact", "primary_service_type"
        ).order_by("-scheduled_start")

    def clean(self):
        cleaned = super().clean()
        issued, due = cleaned.get("issued_on"), cleaned.get("due_on")
        if issued and due and due < issued:
            self.add_error("due_on", "The due date can't be before the issue date.")
        return cleaned

    def save(self, commit=True):
        invoice = super().save(commit=False)
        invoice.contact = invoice.job.contact
        if commit:
            invoice.save()
        return invoice


InvoiceLineFormSet = line_formset(Invoice, InvoiceLineItem)


class PaymentForm(forms.ModelForm):
    """Money received against one invoice. The invoice comes from the
    page you're on, not from a field."""

    class Meta:
        model = Payment
        fields = ["amount", "received_on", "method", "notes"]
        labels = {"received_on": "Received", "notes": "Reference"}
        widgets = {
            "received_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.TextInput(attrs={"placeholder": "Check number, last four digits…"}),
        }

    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.invoice = invoice

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("A payment has to be more than nothing.")
        return amount

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get("amount")
        # Overpayment is allowed — a customer rounds up, or pays two
        # invoices with one check — but it's worth saying out loud.
        if amount and self.invoice is not None and amount > self.invoice.balance:
            self.overpayment = amount - self.invoice.balance
        return cleaned


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["date", "amount", "category", "description"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("An expense has to be more than nothing.")
        return amount
