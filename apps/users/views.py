"""Profiles and the team list (Phase 17 unit 3d). Everyone sees and edits
their own profile; only the Owner sees other people's (ADR 0008)."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import FormView, TemplateView

from apps.crm.audit import record
from apps.crm.models import AuditLogEntry
from apps.jobs.media import send_private_file

from . import throttle
from .forms import (
    AccountForm,
    CrewPayForm,
    MemberAccessForm,
    MemberPasswordForm,
    NewMemberForm,
    ProfileForm,
)
from .models import UserProfile, get_profile
from .roles import (
    ALL_ROLES,
    SALES_ROLES,
    OwnerRequiredMixin,
    Role,
    RoleRequiredMixin,
    roles_for,
    user_role,
)
from .stats import DEFAULT_WINDOW, WINDOWS, crew_sheet, crew_stats, sales_sheet, sales_stats

User = get_user_model()


def _window(request):
    value = request.GET.get("days", "")
    return int(value) if value.isdigit() and int(value) in WINDOWS else DEFAULT_WINDOW


def read_profile(person):
    """This person's profile, or unsaved defaults if they've never saved
    one. Saving creates the row; looking never does."""
    return UserProfile.objects.filter(user=person).first() or UserProfile(user=person)


def profile_context(person, request):
    days = _window(request)
    role = user_role(person)
    is_crew = role == Role.CLEANER or person.job_assignments.exists()
    return {
        "person": person,
        # Read, never create: looking at a profile shouldn't write one.
        # Someone who has never saved theirs reads as empty defaults,
        # the same way the app shell reads a saved theme.
        "person_profile": read_profile(person),
        "person_role": role,
        "days": days,
        "windows": WINDOWS,
        "crew": crew_stats(person, days) if is_crew else None,
        "sales": sales_stats(person, days) if role in SALES_ROLES else None,
        # The same figures over every period, so the trend is readable
        # without loading the page five times. The cards above stay:
        # they carry detail (rating, hours per week, what's upcoming)
        # that does not belong in a row.
        "crew_periods": crew_sheet(person) if is_crew else None,
        "sales_periods": sales_sheet(person) if role in SALES_ROLES else None,
    }


class ProfileView(RoleRequiredMixin, TemplateView):
    allowed_roles = ALL_ROLES
    template_name = "users/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(profile_context(self.request.user, self.request), is_self=True)
        return context


class ProfileEditView(RoleRequiredMixin, TemplateView):
    """Your own name, email, title, phone, and calendar color. A
    self-service change like the password form, so no model permission
    is required beyond having a role."""

    allowed_roles = ALL_ROLES
    template_name = "users/profile_form.html"

    def forms(self, data=None):
        user = self.request.user
        return AccountForm(data, instance=user), ProfileForm(data, instance=get_profile(user))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "account_form" not in kwargs:
            context["account_form"], context["profile_form"] = self.forms()
        return context

    def post(self, request, *args, **kwargs):
        account_form, profile_form = self.forms(request.POST)
        if account_form.is_valid() and profile_form.is_valid():
            with transaction.atomic():
                account_form.save()
                profile_form.save()
            messages.success(request, "Profile updated.")
            return redirect("people:profile")
        return self.render_to_response(
            self.get_context_data(account_form=account_form, profile_form=profile_form)
        )


class TeamListView(OwnerRequiredMixin, TemplateView):
    template_name = "users/team.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        people = (
            # Everyone, including anyone whose sign-in is off — they're
            # still on the team, and this is where it's turned back on.
            User.objects.all()
            .select_related("profile")
            .order_by("-is_active", "first_name", "last_name", "username")
        )
        roles = roles_for(people)
        context["team"] = [(person, roles[person.pk]) for person in people]
        return context


def _pay_state(profile):
    """The two fields the pay form owns, as the log should show them.

    Money as a string so a Decimal does not reach JSON, and the days as
    the words the page shows ("Mon, Tue") rather than the stored "01",
    because a log is only useful if a person can read it.
    """
    return {
        "hourly_rate": "" if profile.hourly_rate is None else str(profile.hourly_rate),
        "working_days": profile.working_days_display or "varies",
    }


def _access_state(person):
    """What the access form can change, as the log should show it.

    Two traps, both found in review (#198):

    - The **group** role, not `user_role()`. A superuser reads as Owner
      whatever groups they hold, so comparing effective roles would show
      no change while the saved group really moved — and the change
      would go unrecorded.
    - Booleans as words. The change-log template passes each value
      through `default`, and `False` is falsy, so turning sign-in off
      rendered as `is_active: True → —`.
    """
    names = set(person.groups.values_list("name", flat=True))
    return {
        "role": next((role.value for role in Role if role.value in names), ""),
        "is_active": "yes" if person.is_active else "no",
    }


class TeamMemberCreateView(OwnerRequiredMixin, FormView):
    """Add somebody to the team (ADR 0021).

    The role and the first password are set here, in one step: there is
    no invite email on this system, so there is nothing for the new
    person to wait for. The owner tells them what it is.
    """

    template_name = "users/member_form.html"
    form_class = NewMemberForm

    def form_valid(self, form):
        # The entry belongs to the same transaction as the account. A
        # failed insert has to take the account with it, or the log
        # quietly stops being the record this feature promises.
        with transaction.atomic():
            person = form.save()
            record(self.request.user, person, AuditLogEntry.Action.CREATED)
        name = person.get_full_name() or person.get_username()
        messages.success(
            self.request,
            f"Added {name}. Tell them their password — they can change it from their own profile.",
        )
        return redirect("people:member", username=person.get_username())


class TeamMemberView(OwnerRequiredMixin, TemplateView):
    """A teammate's profile, and the two things only the Owner sets:
    their hourly rate and the days they normally work."""

    template_name = "users/profile.html"

    def person(self):
        # Inactive people included: turning someone's sign-in off would
        # otherwise remove them from the only page that can turn it back
        # on, which is a one-way door.
        return get_object_or_404(User, username=self.kwargs["username"])

    def get(self, request, *args, **kwargs):
        if kwargs["username"] == request.user.get_username():
            return redirect("people:profile")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self.person()
        context.update(profile_context(person, self.request), is_self=False)
        context.setdefault("pay_form", CrewPayForm(instance=read_profile(person)))
        context.setdefault("access_form", MemberAccessForm(person=person))
        context.setdefault("password_form", MemberPasswordForm(user=person))
        context["is_self_account"] = person == self.request.user
        return context

    def post(self, request, *args, **kwargs):
        person = self.person()
        if "new_password1" in request.POST:
            return self._set_password(request, person)
        if "role" in request.POST or "is_active" in request.POST:
            return self._save_access(request, person)
        form = CrewPayForm(request.POST, instance=get_profile(person))
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(pay_form=form))
        # Same shape as the other three: lock the row, read both states
        # inside the lock, and write the entry before it drops, so a
        # failed insert takes the change with it. The entry hangs off
        # the person rather than their profile row — "Updated Sam" is
        # what the owner is looking for in the log, not "Updated
        # Profile for Sam".
        with transaction.atomic():
            locked = UserProfile.objects.select_for_update().get(pk=form.instance.pk)
            before = _pay_state(locked)
            # Write **only** the two fields this form owns, onto the row
            # as it is now. `form.save()` would write every column of
            # the instance loaded when the page was built, so anything
            # the person changed on their own profile in between — their
            # phone, title, colour, theme — would be silently reverted
            # to what it was when the owner opened the page (#199).
            edited = form.save(commit=False)
            locked.hourly_rate = edited.hourly_rate
            locked.working_days = edited.working_days
            locked.save(update_fields=["hourly_rate", "working_days"])
            after = _pay_state(locked)
            changes = {
                field: [before[field], after[field]]
                for field in before
                if before[field] != after[field]
            }
            if changes:
                record(request.user, person, AuditLogEntry.Action.UPDATED, changes)
        messages.success(
            request, f"Saved pay and working days for {person.get_full_name() or person}."
        )
        return redirect("people:member", username=person.get_username())

    def _set_password(self, request, person):
        """Set somebody else's password (ADR 0021). There is no reset
        email on this system, so this is the only way back in for a
        person who has forgotten theirs."""
        if person == request.user:
            # Same refusal as _save_access, for the same reason: your
            # own password is changed from your own profile, where
            # Django asks for the old one first.
            messages.warning(request, "Change your own password from your profile.")
            return redirect("users:password_change")
        form = MemberPasswordForm(user=person, data=request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(password_form=form))
        # Saving a new hash invalidates every session that person has,
        # because the session auth hash is derived from it. That is the
        # point: a password you reset because an account was shared or
        # stolen has to end the sessions it was used for.
        # The owner asked for these to be recorded (2026-11-03): who
        # changed whose password, and when. Never the password itself,
        # and never the hash — an entry that carried either would turn
        # an Owner-only page into a way to read credentials back out of
        # the log. In one transaction, so a failed insert rolls the new
        # password back rather than leaving it unlogged.
        with transaction.atomic():
            form.save()
            record(
                request.user,
                person,
                AuditLogEntry.Action.UPDATED,
                {"password": [None, "changed"]},
            )
        # Being locked out by the rate limit is one reason the owner is
        # setting this password, and a 429 is returned before any
        # password is checked — so without clearing the count, the new
        # password would not work until the window expired (ADR 0020).
        throttle.forget_username(person.get_username())
        name = person.get_full_name() or person.get_username()
        messages.success(
            request,
            f"New password set for {name}. Tell them what it is — "
            "they can change it from their own profile.",
        )
        return redirect("people:member", username=person.get_username())

    def _save_access(self, request, person):
        if person == request.user:
            # The GET redirects you to your own profile; a POST has to
            # refuse too, or you could take away your own access and
            # have no way back in.
            messages.warning(request, "You can't change your own access from here.")
            return redirect("people:profile")
        form = MemberAccessForm(request.POST, person=person)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(access_form=form))
        # Lock the row first and read both states inside that lock.
        # `MemberAccessForm.save` takes the same lock, so every writer
        # serialises on this row — read `before` outside it and two
        # owners saving at once can produce an entry describing a
        # transition that never happened, or none at all (#198).
        with transaction.atomic():
            locked = User.objects.select_for_update().get(pk=person.pk)
            before = _access_state(locked)
            form.save()
            locked.refresh_from_db()
            after = _access_state(locked)
            changes = {
                field: [before[field], after[field]]
                for field in before
                if before[field] != after[field]
            }
            if changes:
                record(request.user, locked, AuditLogEntry.Action.UPDATED, changes)
        name = person.get_full_name() or person.get_username()
        messages.success(request, f"Saved what {name} can reach.")
        return redirect("people:member", username=person.get_username())


class ThemeView(LoginRequiredMixin, View):
    """Save light / dark / match-my-device. The page script posts here
    and flips the theme in place (204); without JS it's a plain form
    post that comes back to the page."""

    def post(self, request, *args, **kwargs):
        value = request.POST.get("theme")
        if value not in UserProfile.Theme.values:
            return HttpResponseBadRequest("Unknown theme")
        profile = get_profile(request.user)
        profile.theme = value
        profile.save(update_fields=["theme"])
        if request.headers.get("X-Requested-With") == "fetch":
            return HttpResponse(status=204)
        next_url = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            next_url = "/"
        return redirect(next_url)


class AvatarView(RoleRequiredMixin, View):
    """Someone's profile picture, to people who work here.

    Profile pictures live under `media/private/` like job photos, and
    for the same reason: a photograph of a colleague isn't something to
    leave on a public URL. Anyone with a role may see any teammate's —
    they work together — but a signed-out visitor may not.
    """

    allowed_roles = ALL_ROLES

    def get(self, request, username, *args, **kwargs):
        person = get_object_or_404(User, username=username)
        profile = UserProfile.objects.filter(user=person).first()
        if profile is None or not profile.photo:
            raise Http404("No photo")
        return send_private_file(profile.photo)
