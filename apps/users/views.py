"""Profiles and the team list (Phase 17 unit 3d). Everyone sees and edits
their own profile; only the Owner sees other people's (ADR 0008)."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from .forms import AccountForm, CrewPayForm, ProfileForm
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
from .stats import DEFAULT_WINDOW, WINDOWS, crew_stats, sales_stats

User = get_user_model()


def _window(request):
    value = request.GET.get("days", "")
    return int(value) if value.isdigit() and int(value) in WINDOWS else DEFAULT_WINDOW


def profile_context(person, request):
    days = _window(request)
    role = user_role(person)
    is_crew = role == Role.CLEANER or person.job_assignments.exists()
    return {
        "person": person,
        "person_profile": get_profile(person),
        "person_role": role,
        "days": days,
        "windows": WINDOWS,
        "crew": crew_stats(person, days) if is_crew else None,
        "sales": sales_stats(person, days) if role in SALES_ROLES else None,
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
            User.objects.filter(is_active=True)
            .select_related("profile")
            .order_by("first_name", "last_name", "username")
        )
        roles = roles_for(people)
        context["team"] = [(person, roles[person.pk]) for person in people]
        return context


class TeamMemberView(OwnerRequiredMixin, TemplateView):
    """A teammate's profile, and the two things only the Owner sets:
    their hourly rate and the days they normally work."""

    template_name = "users/profile.html"

    def person(self):
        return get_object_or_404(User, username=self.kwargs["username"], is_active=True)

    def get(self, request, *args, **kwargs):
        if kwargs["username"] == request.user.get_username():
            return redirect("people:profile")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self.person()
        context.update(profile_context(person, self.request), is_self=False)
        context.setdefault("pay_form", CrewPayForm(instance=get_profile(person)))
        return context

    def post(self, request, *args, **kwargs):
        person = self.person()
        form = CrewPayForm(request.POST, instance=get_profile(person))
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(pay_form=form))
        form.save()
        messages.success(
            request, f"Saved pay and working days for {person.get_full_name() or person}."
        )
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
