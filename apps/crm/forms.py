from django import forms
from django.db import transaction
from django.db.models import Q

from apps.jobs.access import quotes_for

from .models import (
    Activity,
    BusinessPlan,
    Company,
    Contact,
    Note,
    PlanChecklistItem,
    Property,
    Task,
)


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


class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = [
            "activity_type",
            "subject",
            "description",
            "company",
            "contact",
        ]

    def clean(self):
        # The DB-level "at least one relation" constraint was removed
        # (docs/DATABASE_REVIEW.md finding #2 — an Activity may
        # legitimately degrade to zero relations if the things it once
        # referenced get deleted), but a *new* Activity should still be
        # tagged to at least one record on creation. Enforced here, at
        # the form layer, per docs/DATABASE_DESIGN.md's plan for this.
        cleaned_data = super().clean()
        if not any(cleaned_data.get(field) for field in ("company", "contact")):
            raise forms.ValidationError("An activity needs to be linked to a company or a contact.")
        return cleaned_data


class PropertyForm(forms.ModelForm):
    """A service address.

    The app has had no address form at all until now: addresses could
    only be created through the Django admin, which is why booking a
    job for a new customer meant leaving the app. Phase 18.5 unit 3.

    Coordinates are not asked for. They are the geocoder's business
    (apps/crm/geocoding.py), and `located_address` is `editable=False`
    anyway, so editing a street here re-opens the lookup by itself.
    """

    class Meta:
        model = Property
        fields = [
            "contact",
            "label",
            "street",
            "city",
            "state",
            "postal_code",
            "is_primary",
            "notes",
        ]
        labels = {
            "contact": "Customer",
            "label": "What it is",
            "postal_code": "Postal code",
            "is_primary": "Their main address",
        }
        help_texts = {
            "label": "e.g. Home, Rental",
            "is_primary": "Choosing this moves it off whichever address held it before.",
        }
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contact"] = ContactChoiceField(
            queryset=contact_choices(self.instance.contact_id), label="Customer"
        )

    def _post_clean(self):
        # `one_primary_property_per_contact` is a partial unique index,
        # and this form resolves it itself: save() steps the previous
        # main address down in the same transaction. Django checks
        # constraints during validation, before that can happen, so
        # left alone it rejects a change that is about to be perfectly
        # valid — "Constraint is violated" shown to someone ticking a
        # box that is meant to move.
        #
        # Only skipped when the box is actually ticked, and the
        # database still enforces it either way.
        if self.data.get("is_primary"):
            self._validate_constraints = False
        super()._post_clean()

    def save(self, commit=True):
        if not (commit and self.cleaned_data.get("is_primary")):
            return super().save(commit)
        with transaction.atomic():
            # Demote first: the index is not deferrable, so there must
            # never be an instant with two.
            Property.objects.filter(contact=self.cleaned_data["contact"], is_primary=True).exclude(
                pk=self.instance.pk
            ).update(is_primary=False)
            return super().save(commit=True)


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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # This used to ask for a Deal, which had been empty since
        # Phase 17 folded every one into a Quote; the model itself was
        # retired in Phase 18 unit 5.
        self.fields["contact"] = ContactChoiceField(
            queryset=contact_choices(self.instance.contact_id),
            # Task.contact is null=True/blank=True: a general to-do
            # needn't name anyone. clean_contact() still insists for a
            # follow-up, which the database also checks.
            required=False,
            label="Customer",
        )
        # Scoped through the access helper rather than Quote.objects:
        # today every sales role sees every estimate, so this is the
        # same set — but it means the form follows the rule rather than
        # restating it, if that ever narrows.
        self.fields["quote"].queryset = (
            (quotes_for(user) if user else self.fields["quote"].queryset)
            .select_related("contact")
            .order_by("-pk")
        )

    def clean_contact(self):
        # A follow-up must name its customer (DB check
        # follow_up_has_contact_and_service); catch that here as a form
        # error instead of letting the save fail with a 500.
        contact = self.cleaned_data.get("contact")
        if self.instance.kind == Task.Kind.FOLLOW_UP and contact is None:
            raise forms.ValidationError("A follow-up needs its customer.")
        return contact

    def clean(self):
        cleaned = super().clean()
        contact, quote = cleaned.get("contact"), cleaned.get("quote")
        # Two fields that must agree are two fields that can disagree:
        # a task naming one customer and another customer's estimate
        # would show the wrong person beside the work. Same guard, and
        # the same reasoning, as JobForm's address check.
        if contact and quote and quote.contact_id != contact.pk:
            self.add_error("quote", "That estimate belongs to a different customer.")
        return cleaned


class BusinessPlanForm(forms.ModelForm):
    """A piece of work on the business rather than in it.

    The app has had no plan form at all until now: plans could only be
    created through the Django admin, which is why `plan_detail.html`
    carried the line "Editing plans and ticking off steps arrives in
    Phase 19". This is that.
    """

    class Meta:
        model = BusinessPlan
        fields = ["title", "description", "owner", "due_date", "status", "priority"]
        labels = {"due_date": "Aim to finish by", "owner": "Whose it is"}
        help_texts = {
            "due_date": "Optional. A plan without a date sorts to the end of the list.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only people who could actually act on it. A plan assigned to a
        # crew member would sit on a page they cannot open — the Tasks
        # hub is sales-and-owner, and `users/0004` gives cleaners no
        # businessplan permissions at all.
        from apps.users.roles import Role

        self.fields["owner"].queryset = (
            self.fields["owner"]
            .queryset.filter(
                is_active=True,
                groups__name__in=[Role.OWNER.value, Role.SALES_REP.value],
            )
            .distinct()
            .order_by("first_name", "last_name", "username")
        )


class ChecklistItemForm(forms.ModelForm):
    """One step on a plan.

    Deliberately one field. Steps get added as they are thought of,
    usually several in a row, so anything more than a single box and a
    button gets in the way.
    """

    class Meta:
        model = PlanChecklistItem
        fields = ["text"]
        labels = {"text": "Next step"}
        widgets = {
            "text": forms.TextInput(
                attrs={"placeholder": "e.g. Price up the van wrap", "autocomplete": "off"}
            )
        }


class NoteForm(forms.ModelForm):
    """A note: general, about a customer, or about a job.

    Until now notes could only be written in the Django admin, which
    is why `NoteListView`'s docstring said "Adding and editing notes
    lands in Phase 19".
    """

    class Meta:
        model = Note
        fields = ["body", "contact", "job", "pinned"]
        labels = {
            "body": "The note",
            "contact": "About a customer",
            "job": "About a job",
            "pinned": "Keep it at the top",
        }
        help_texts = {
            "job": "Optional. Shown on that job's page.",
        }
        widgets = {"body": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Said on the form rather than left to be discovered: a note
        # about a customer is readable by any crew member assigned to
        # any of that customer's jobs, which is the owner's deliberate
        # choice and not obvious while writing one.
        #
        # The wording is "one of this customer's jobs", not "this
        # customer's address", and the difference is the point. The job
        # page filters notes by **contact**, not by address
        # (`JobDetailView`), so a customer with three addresses has
        # their notes readable by a crew member on any one of those
        # jobs. Review caught the first version of this text
        # understating its own warning, which is the worst thing a
        # warning can do.
        self.fields["contact"] = ContactChoiceField(
            queryset=contact_choices(self.instance.contact_id),
            required=False,
            label="About a customer",
            help_text=(
                "Optional. Any crew member assigned to one of this customer's "
                "jobs can read notes about them — at any of their addresses — "
                "so keep commercial detail out of these."
            ),
        )
        self.fields["job"].queryset = (
            self.fields["job"].queryset.select_related("contact").order_by("-scheduled_start")
        )
        self.fields["job"].required = False

    def clean(self):
        cleaned = super().clean()
        contact, job = cleaned.get("contact"), cleaned.get("job")
        # Two fields that must agree are two fields that can disagree —
        # the same guard TaskForm and JobForm already apply. A note
        # filed against one customer and another customer's job would
        # show up in both places, each time beside the wrong person.
        if contact and job and job.contact_id != contact.pk:
            self.add_error("job", "That job belongs to a different customer.")
        return cleaned


class JobNoteForm(forms.ModelForm):
    """A note about one job, written from the job's own page.

    One field, because the job is already decided by the page you are
    on and the person writing it is standing at the kerb. `users/0004`
    gives crews `add_note` for exactly this — "Crews update their own
    jobs (status, hours) and add photos/notes" — and nothing had ever
    built it.
    """

    class Meta:
        model = Note
        fields = ["body"]
        labels = {"body": "Add a note about this job"}
        widgets = {
            "body": forms.Textarea(
                attrs={"rows": 3, "placeholder": "e.g. Gate code 4821, side entrance"}
            )
        }
