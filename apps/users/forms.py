from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

from .models import UserProfile
from .roles import Role, user_role

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


class MemberAccessForm(forms.Form):
    """What the Owner decides about a teammate: what they can reach, and
    whether they can sign in at all (Phase 17.5 step 10).

    Roles were admin-only until now. Keeping it to one role apiece
    matches how the rest of the app asks the question (ADR 0008).
    """

    role = forms.ChoiceField(
        choices=[("", "No role — can sign in but sees nothing")]
        + [(role.value, role.value) for role in Role],
        required=False,
        label="Role",
        help_text="What they can reach. Changing it takes effect the next time they load a page.",
    )
    is_active = forms.BooleanField(
        required=False,
        label="Can sign in",
        help_text="Turning this off keeps all their work and history, and stops them signing in.",
        widget=forms.CheckboxInput(attrs={"class": "switch"}),
    )

    def __init__(self, *args, person=None, **kwargs):
        self.person = person
        if person is not None and "initial" not in kwargs:
            current = user_role(person)
            kwargs["initial"] = {
                "role": current.value if current else "",
                "is_active": person.is_active,
            }
        super().__init__(*args, **kwargs)

    def save(self):
        """One transaction, with the row locked: the role and the
        sign-in flag are one decision, and two owners saving at once
        must not leave someone holding two roles or half a change."""
        role = self.cleaned_data["role"]
        with transaction.atomic():
            person = get_user_model().objects.select_for_update().get(pk=self.person.pk)
            groups = Group.objects.filter(name__in=[r.value for r in Role])
            person.groups.remove(*groups)
            if role:
                person.groups.add(Group.objects.get(name=role))
            person.is_active = self.cleaned_data["is_active"]
            person.save(update_fields=["is_active"])
        self.person = person
        return person
