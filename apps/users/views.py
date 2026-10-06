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
from django.views.generic import TemplateView

from apps.jobs.media import send_private_file

from .forms import AccountForm, CrewPayForm, MemberAccessForm, ProfileForm
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
        context["is_self_account"] = person == self.request.user
        return context

    def post(self, request, *args, **kwargs):
        person = self.person()
        if "role" in request.POST or "is_active" in request.POST:
            return self._save_access(request, person)
        form = CrewPayForm(request.POST, instance=get_profile(person))
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(pay_form=form))
        form.save()
        messages.success(
            request, f"Saved pay and working days for {person.get_full_name() or person}."
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
        form.save()
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
