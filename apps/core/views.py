import json
import logging
import re
from datetime import timedelta
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Count, F, Q, Sum
from django.http import (
    FileResponse,
    Http404,
    HttpResponseBadRequest,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import redirect, render
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.crm.followups import add_months
from apps.crm.models import Activity, Company, Contact, Deal, Lead, Task
from apps.jobs import reports
from apps.jobs.access import jobs_for, quotes_for
from apps.jobs.calendar import day_bounds
from apps.jobs.models import Job, JobAssignment, Quote
from apps.jobs.reports import invoiced_revenue, outstanding
from apps.messaging.services import unread_count
from apps.users.models import get_profile
from apps.users.roles import OwnerRequiredMixin, Role, SalesRoleRequiredMixin, user_role

from . import export, goals, notifications, onboarding, pwa
from .branding import process_logo
from .forms import BusinessSettingsForm, GoalsForm, LinkFormSet, LogoForm
from .models import BusinessLink, Notification
from .navigation import quick_actions
from .pagination import PerPageMixin
from .templatetags.crm_format import money

logger = logging.getLogger(__name__)

# Caps each category's results rather than paginating each one
# separately — simpler, and a search this wide (five models at once)
# should point the user to a more specific query long before this
# limit matters (CLAUDE.md's Performance Rules: paginate user-facing
# lists, don't load unbounded record sets).
SEARCH_RESULTS_PER_MODEL = 20

# Same reasoning for the dashboard's bounded lists (my tasks, recent
# activity) — a fixed cap instead of pagination on a page meant for an
# at-a-glance summary, not a full record browser.
DASHBOARD_LIST_LIMIT = 10

# Upcoming site visits: today and the next six days.
VISIT_DAYS = 7


class DashboardView(LoginRequiredMixin, TemplateView):
    """The role-aware home screen (ADR 0010, Phase 17.5 step 4).

    Everyone gets a greeting, their own overview cards, today's jobs, and
    shortcut tiles. The Owner also gets the setup checklist until it's
    finished, revenue cards with a month-to-date mini chart, and progress
    against the monthly goals. A Sales Rep sees their own pipeline; a
    Cleaner sees their own work and hours. Revenue never reaches a
    non-Owner.

    Every figure is a database aggregate, scoped through
    apps/jobs/access.py, and money figures come from
    apps/jobs/reports.py so this page and Financials always agree.
    """

    template_name = "core/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        role = user_role(user)
        context["role"] = role
        if role is None:
            return context

        now = timezone.localtime()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        day_start, day_end = day_bounds(today, today)
        context.update(
            greeting=_greeting(now.hour),
            today=today,
            quick_actions=quick_actions(user),
            unread_messages=unread_count(user),
        )

        jobs = jobs_for(user).exclude(status=Job.Status.CANCELLED)
        todays_jobs = jobs.filter(scheduled_start__gte=day_start, scheduled_start__lt=day_end)
        todays_count = todays_jobs.count()
        context["todays_job_count"] = todays_count
        context["todays_jobs"] = (
            todays_jobs.select_related("contact", "service_property", "primary_service_type")
            .prefetch_related("crew")
            .order_by("scheduled_start", "pk")[:DASHBOARD_LIST_LIMIT]
        )

        if role == Role.CLEANER:
            self._cleaner(context, user, jobs, week_start, today, day_end, todays_count)
            return context
        self._sales(context, user, role, today, week_start, todays_count)
        return context

    # ---------- Per-role figures ----------

    def _cleaner(self, context, user, jobs, week_start, today, day_end, todays_count):
        context["upcoming_jobs"] = (
            jobs.filter(scheduled_start__gte=day_end, status=Job.Status.SCHEDULED)
            .select_related("contact", "service_property", "primary_service_type")
            .prefetch_related("crew")
            .order_by("scheduled_start", "pk")[:DASHBOARD_LIST_LIMIT]
        )
        week = JobAssignment.objects.filter(
            user=user,
            job__status=Job.Status.COMPLETED,
            job__completed_at__gte=day_bounds(week_start, today)[0],
        )
        hours = week.aggregate(total=Sum("hours_worked"))["total"] or 0
        done = week.count()
        context["jobs_done_this_week"] = done
        context["hours_this_week"] = hours
        context["cards"] = [
            _card("Jobs today", todays_count, "Assigned to you", url=reverse("jobs:calendar")),
            _card("Done this week", done, "Completed jobs", accent="green"),
            _card("Hours this week", hours, "Logged on completed jobs", accent="purple"),
            _card(
                "Unread messages",
                context["unread_messages"],
                "Team chat",
                url=reverse("messaging:home"),
                accent="orange",
            ),
        ]

    def _sales(self, context, user, role, today, week_start, todays_count):
        is_owner = role == Role.OWNER
        context["is_owner"] = is_owner
        open_quotes = quotes_for(user).filter(status__in=Quote.OPEN_STATUSES)
        follow_ups = Task.objects.filter(kind=Task.Kind.FOLLOW_UP, status=Task.Status.PENDING)
        visit_start, visit_end = day_bounds(today, today + timedelta(days=VISIT_DAYS - 1))
        visits = quotes_for(user).filter(
            site_visit_at__gte=visit_start,
            site_visit_at__lt=visit_end,
            status__in=Quote.OPEN_STATUSES,
        )
        if not is_owner:
            open_quotes = open_quotes.filter(prepared_by=user)
            follow_ups = follow_ups.filter(assigned_to=user)
            visits = visits.filter(prepared_by=user)

        quote_totals = open_quotes.with_totals().aggregate(
            count=Count("pk"), total=Sum("total_amount")
        )
        due = follow_ups.filter(due_date__lte=today).count()
        overdue = follow_ups.filter(due_date__lt=today).count()
        context["open_quotes"] = quote_totals
        context["follow_ups_due"] = due
        context["follow_ups_overdue"] = overdue
        context["site_visits"] = visits.select_related("contact", "service_property").order_by(
            "site_visit_at", "pk"
        )[:DASHBOARD_LIST_LIMIT]
        context["my_tasks"] = (
            Task.objects.filter(assigned_to=user, status=Task.Status.PENDING)
            .select_related("contact", "service_type")
            .order_by(F("due_date").asc(nulls_last=True), "pk")[:DASHBOARD_LIST_LIMIT]
        )
        context["recent_activities"] = Activity.objects.select_related(
            "created_by", "company", "contact"
        )[:DASHBOARD_LIST_LIMIT]

        if not is_owner:
            context["cards"] = [
                _card(
                    "Your open estimates",
                    quote_totals["count"],
                    f"{money(quote_totals['total'] or 0)} in drafts and sent",
                    url=reverse("jobs:quote_list"),
                ),
                _card(
                    "Follow-ups due",
                    due,
                    f"{overdue} overdue" if overdue else "None overdue",
                    url=reverse("crm:task_followups") + "?mine=1",
                    accent="orange" if overdue else "green",
                ),
                _card("Jobs today", todays_count, "Whole team", url=reverse("jobs:calendar")),
                _card(
                    "Unread messages",
                    context["unread_messages"],
                    "Team chat",
                    url=reverse("messaging:home"),
                    accent="purple",
                ),
            ]
            return

        self._owner(context, today, week_start)

    def _owner(self, context, today, week_start):
        month_first = goals.month_start(today)
        period = reports.Period("month", month_first, today)
        figures = reports.summary(period)
        unpaid = outstanding()
        context["outstanding"] = unpaid
        # Same stretch of the previous month, so a comparison on the 3rd
        # isn't a whole month against three days.
        previous_first = add_months(month_first, -1)
        previous_last = min(add_months(today, -1), add_months(month_first, 0) - timedelta(days=1))
        previous = (
            invoiced_revenue(previous_first, previous_last)
            if previous_last >= previous_first
            else None
        )
        _, buckets = reports.trend(period)
        # Today and this week stay on the card's second line: the design
        # is month-first, but a day's takings are what an owner checks.
        context["revenue_today"] = invoiced_revenue(today, today)
        context["revenue_week"] = invoiced_revenue(week_start, today)
        context["revenue_spark"] = reports.sparkline(buckets)
        context["revenue_change"] = reports.change(figures["revenue"], previous)
        context["month_label"] = f"{today:%B}"
        context["cards"] = [
            _card(
                "Revenue this month",
                money(figures["revenue"]),
                f"{money(context['revenue_today'])} today · "
                f"{money(context['revenue_week'])} this week",
                url=reverse("jobs:financials") + "?range=month",
                spark=True,
                change=context["revenue_change"],
            ),
            _card(
                "Collected",
                money(figures["collected"]),
                "Payments received this month",
                url=reverse("jobs:financials") + "?range=month",
                accent="green",
            ),
            _card(
                "Outstanding",
                money(unpaid["total"]),
                f"{unpaid['count']} unpaid invoice{pluralize(unpaid['count'])}",
                url=reverse("jobs:financials") + "#outstanding",
                accent="orange" if unpaid["count"] else "green",
            ),
            _card(
                "Jobs completed",
                figures["jobs_completed"],
                f"This month · {figures['invoice_count']} invoice"
                f"{pluralize(figures['invoice_count'])} sent",
                url=reverse("jobs:calendar"),
                accent="purple",
            ),
        ]
        context["goals"] = goals.progress(today)
        context["onboarding"] = onboarding.checklist(
            self.request.business, get_profile(self.request.user)
        )


def _greeting(hour):
    if hour < 12:
        return "Good morning"
    return "Good afternoon" if hour < 18 else "Good evening"


def _card(label, value, meta="", url="", accent="blue", spark=False, change=None):
    """One overview card. Every card carries an accent (blue unless it
    says otherwise) because the tint, hover border, and value color all
    read from it — the first card is the tinted one, matching the
    reference design."""
    return {
        "label": label,
        "value": value,
        "meta": meta,
        "url": url,
        "accent": accent,
        "spark": spark,
        "change": change,
    }


class GoalsView(OwnerRequiredMixin, TemplateView):
    """The monthly targets the dashboard measures against."""

    template_name = "core/goals.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("form", GoalsForm())
        context["progress"] = goals.progress(timezone.localdate())
        return context

    def post(self, request, *args, **kwargs):
        form = GoalsForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        form.save()
        messages.success(request, "Monthly goals saved.")
        return redirect("core:goals")


class NotificationListView(LoginRequiredMixin, PerPageMixin, ListView):
    """Everything this person has been told, newest first."""

    template_name = "core/notifications.html"
    context_object_name = "notifications"

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unread"] = notifications.unread_notifications(self.request.user).count()
        return context


class NotificationReadView(LoginRequiredMixin, View):
    """Mark one notification read and go where it points. Someone else's
    notification is simply not found."""

    def post(self, request, pk, *args, **kwargs):
        notification = notifications.mark_read(request.user, pk)
        if notification is None:
            raise Http404("No such notification")
        return redirect(notification.url or reverse("core:notifications"))


class NotificationReadAllView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        notifications.mark_all_read(request.user)
        return redirect(_safe_next(request, reverse("core:notifications")))


class OnboardingDismissView(OwnerRequiredMixin, View):
    """Hide the setup checklist for good."""

    def post(self, request, *args, **kwargs):
        profile = get_profile(request.user)
        profile.onboarding_dismissed = True
        profile.save(update_fields=["onboarding_dismissed"])
        return redirect(_safe_next(request, reverse("core:index")))


def _safe_next(request, fallback):
    """A "next" from the form, but only a path on this site — never an
    absolute URL someone put in a link."""
    target = request.POST.get("next", "")
    return target if target.startswith("/") and not target.startswith("//") else fallback


def _search(query):
    """Global search across Company/Contact/Lead/Deal/Task.

    Activity is deliberately excluded — it has no detail page of its
    own (its "detail page" is the timeline on whichever record it's
    attached to; see apps/crm/views.py's ActivityCreateView docstring),
    so a search result for one would have nowhere sensible to link to.

    Each queryset adds "pk" as a secondary sort key, on top of each
    model's own Meta.ordering. Meta.ordering alone (e.g. Task's
    `due_date`, Lead/Deal's `-created_at`) already makes results
    deterministic in the common case, but ties on that field (several
    tasks with no due date, two deals created in the same instant)
    would otherwise have no guaranteed relative order — meaning which
    rows land inside the [:20] cap could vary between requests.
    """
    return {
        "companies": Company.objects.filter(name__icontains=query).order_by("name", "pk")[
            :SEARCH_RESULTS_PER_MODEL
        ],
        "contacts": Contact.objects.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )
        .select_related("company")
        .order_by("last_name", "first_name", "pk")[:SEARCH_RESULTS_PER_MODEL],
        "leads": Lead.objects.filter(
            Q(name__icontains=query) | Q(company_name__icontains=query) | Q(email__icontains=query)
        ).order_by("-created_at", "pk")[:SEARCH_RESULTS_PER_MODEL],
        "deals": Deal.objects.filter(title__icontains=query)
        .select_related("company", "contact")
        .order_by("-created_at", "pk")[:SEARCH_RESULTS_PER_MODEL],
        "tasks": Task.objects.filter(title__icontains=query)
        .select_related("assigned_to")
        .order_by("due_date", "pk")[:SEARCH_RESULTS_PER_MODEL],
        **_documents_by_number(query),
    }


# "J-1502", "q1067", "Q 1067": document numbers are 1000 + the primary key.
DOCUMENT_NUMBER = re.compile(r"^\s*([jq])[-\s]?(\d{1,9})\s*$", re.IGNORECASE)


def _documents_by_number(query):
    match = DOCUMENT_NUMBER.match(query)
    if not match:
        return {"jobs": [], "quotes": []}
    prefix, pk = match.group(1).upper(), int(match.group(2)) - 1000
    model = Job if prefix == "J" else Quote
    found = list(model.objects.filter(pk=pk).select_related("contact"))
    return {"jobs": found if prefix == "J" else [], "quotes": found if prefix == "Q" else []}


class HealthCheckView(View):
    """Liveness/readiness check for compose.{dev,prod}.yml's `web`
    healthcheck (Phase 12) — the thing Phase 7's original TCP-connect
    check deferred to this phase, since a plain TCP connect only
    proves gunicorn is listening, not that Django can actually reach
    PostgreSQL. Deliberately unauthenticated (monitoring/orchestration
    tooling can't log in) and GET-only (Django's plain `View` already
    405s any other method) — no CSRF token needed since this never
    changes state. Returns no information beyond "ok"/"error" per
    component; a monitoring tool has no legitimate need for anything
    more specific than that.
    """

    def get(self, request, *args, **kwargs):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            # Deliberately broad: any failure reaching the database —
            # not just the specific exceptions psycopg2/Django raise
            # for a downed connection — means this endpoint should
            # report unhealthy, not crash trying to be more precise
            # about which exception it was.
            logger.exception("Health check failed: could not reach the database")
            return JsonResponse({"status": "error", "database": "error"}, status=503)
        return JsonResponse({"status": "ok", "database": "ok"})


class ManifestView(View):
    """Web app manifest (installable PWA). Public — browsers fetch it
    without credentials — and contains nothing sensitive."""

    def get(self, request, *args, **kwargs):
        business = getattr(request, "business", None)
        name = business.name if business is not None else ""
        return JsonResponse(pwa.manifest(name), content_type="application/manifest+json")


class ServiceWorkerView(View):
    """Serves the service worker from the site root so its scope covers
    the whole app (a worker under /static/ could only control /static/).
    no-cache makes the browser revalidate it on every update check."""

    def get(self, request, *args, **kwargs):
        response = render(
            request,
            "core/sw.js",
            {
                "version": pwa.asset_version(),
                "offline_url": reverse("core:offline"),
                "precache_json": json.dumps(pwa.precache_urls()),
                "network_first_assets": settings.DEBUG,
            },
            content_type="application/javascript",
        )
        response["Cache-Control"] = "no-cache"
        return response


class OfflineView(TemplateView):
    """What the service worker shows when a page can't be loaded — no
    user data, so it's safe to cache and to show logged out."""

    template_name = "offline.html"


class SearchView(SalesRoleRequiredMixin, TemplateView):
    template_name = "core/search.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        context["query"] = query
        if query:
            results = _search(query)
            context["results"] = results
            context["has_results"] = any(results.values())
        return context


class StyleguideForm(forms.Form):
    """Sample fields for the style guide — never saved."""

    business_name = forms.CharField(
        initial="Sample Exterior Co.", help_text="Leave blank if you're operating as a freelancer"
    )
    owner_name = forms.CharField(
        initial="Alex Morgan",
        disabled=True,
        help_text="This is your registered name and cannot be changed",
    )
    contact_email = forms.EmailField(initial="alex@example.com")
    service = forms.ChoiceField(
        choices=[("windows", "Window cleaning"), ("gutters", "Gutter cleaning")]
    )
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)
    active = forms.BooleanField(initial=True, required=False)


class StyleguideView(OwnerRequiredMixin, TemplateView):
    """Every shared component on one page, with made-up sample data
    (docs/decisions/0010). Owner-only: it's a design reference, not a
    working page."""

    template_name = "core/styleguide.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = StyleguideForm()
        context["page_obj"] = Paginator(range(137), 10).get_page(3)
        context["people"] = [
            "Alex Morgan",
            "Jamie Rivera",
            "Sam Patel",
            "Riley Chen",
            "Casey Brooks",
        ]
        context["accents"] = ["blue", "green", "orange", "red", "purple", "teal", "sky", "slate"]
        # A made-up series, so the mini chart has the same geometry here
        # as on the dashboard (reports.sparkline, not hand-written SVG).
        context["sg_spark"] = reports.sparkline(
            [
                {"start": None, "revenue": Decimal(amount)}
                for amount in (120, 0, 340, 210, 560, 90, 480, 300, 620, 150)
            ]
        )
        context["nav_icons"] = [
            "dashboard",
            "inbox",
            "customers",
            "crew",
            "job",
            "finance",
            "map",
            "reports",
            "messages",
            "logout",
            "ideas",
            "bug",
            "settings",
            "profile",
        ]
        return context


SUGGEST_LIMIT = 8


class SearchSuggestView(SalesRoleRequiredMixin, View):
    """Top matches for the command palette (⌘K), as JSON. The full
    search page stays the no-JS path and the place to see everything."""

    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip()
        if len(query) < 2:
            return JsonResponse({"results": []})
        results = _search(query)
        rows = (
            [
                {
                    "label": job.number,
                    "detail": str(job.contact),
                    "url": job.get_absolute_url(),
                    "kind": "Job",
                }
                for job in results["jobs"]
            ]
            + [
                {
                    "label": q.number,
                    "detail": str(q.contact),
                    "url": q.get_absolute_url(),
                    "kind": "Estimate",
                }
                for q in results["quotes"]
            ]
            + [
                {
                    "label": str(c),
                    "detail": c.phone or c.email,
                    "url": c.get_absolute_url(),
                    "kind": "Customer",
                }
                for c in results["contacts"]
            ]
            + [
                {"label": c.name, "detail": "", "url": c.get_absolute_url(), "kind": "Company"}
                for c in results["companies"]
            ]
            + [
                {"label": t.title, "detail": "", "url": t.get_absolute_url(), "kind": "Task"}
                for t in results["tasks"]
            ]
        )
        return JsonResponse({"results": rows[:SUGGEST_LIMIT]})


class BusinessSettingsView(OwnerRequiredMixin, TemplateView):
    """Business Information (name, logo, contact details, links,
    currency) and Export Data. Owner only (ADR 0008)."""

    template_name = "core/business_settings.html"

    def forms(self, data=None, files=None):
        # load() gives the saved row, or unsaved defaults (pk=1) that the
        # first save inserts.
        business = self.request.business
        return (
            BusinessSettingsForm(data, instance=business),
            LogoForm(data, files),
            LinkFormSet(data, queryset=BusinessLink.objects.all(), prefix="links"),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "form" not in kwargs:
            context["form"], context["logo_form"], context["links"] = self.forms()
        context["owner_name"] = (
            self.request.user.get_full_name() or self.request.user.get_username()
        )
        context["datasets"] = [(key, label) for key, (label, _) in export.DATASETS.items()]
        return context

    def post(self, request, *args, **kwargs):
        form, logo_form, links = self.forms(request.POST, request.FILES)
        new_logo = None
        if form.is_valid() and logo_form.is_valid():
            upload = logo_form.cleaned_data.get("logo_file")
            if upload:
                try:
                    new_logo = process_logo(upload, logo_form.crop())
                except ValidationError as error:
                    logo_form.add_error("logo_file", error)
        if not (form.is_valid() and logo_form.is_valid() and links.is_valid()):
            return self.render_to_response(
                self.get_context_data(form=form, logo_form=logo_form, links=links)
            )

        business = form.save(commit=False)
        old_logo = business.logo.name if business.logo else ""
        if new_logo is not None:
            business.logo.save("logo.png", new_logo, save=False)
        elif logo_form.cleaned_data.get("remove_logo"):
            business.logo = ""
        with transaction.atomic():
            business.save()
            for link in links.save(commit=False):
                link.save()
            for link in links.deleted_objects:
                link.delete()
            # Number every surviving row the way the page listed them, so
            # an added link lands last instead of sharing position 0 with
            # the first one (save(commit=False) returns only new and
            # changed rows).
            kept = [
                form.instance
                for form in links.forms
                if form.instance.pk and form not in links.deleted_forms
            ]
            for position, link in enumerate(kept):
                if link.position != position:
                    link.position = position
                    link.save(update_fields=["position"])
        # Remove the replaced file only once the new state is saved.
        if old_logo and old_logo != (business.logo.name if business.logo else ""):
            business.logo.storage.delete(old_logo)
        messages.success(request, "Business settings saved.")
        return redirect("core:business_settings")


class BusinessExportView(OwnerRequiredMixin, View):
    """Download one dataset as CSV or JSON (apps/core/export.py)."""

    def get(self, request, *args, **kwargs):
        dataset = request.GET.get("dataset", "")
        fmt = request.GET.get("format", "csv")
        if dataset not in export.DATASETS or fmt not in export.FORMATS:
            return HttpResponseBadRequest("Unknown dataset or format")
        rows = export.DATASETS[dataset][1]()
        if fmt == "csv":
            body, content_type = export.stream_csv(rows), "text/csv; charset=utf-8"
        else:
            body, content_type = export.stream_json(rows), "application/json"
        response = StreamingHttpResponse(body, content_type=content_type)
        filename = f"{dataset}-{timezone.localdate().isoformat()}.{fmt}"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class BusinessLogoView(View):
    """The uploaded logo. Public: the login page shows it too, and a logo
    isn't private. Cacheable — the URL carries a version (?v=) that
    changes on every save."""

    def get(self, request, *args, **kwargs):
        business = request.business
        if not business.logo:
            raise Http404("No logo")
        response = FileResponse(business.logo.open("rb"), content_type="image/png")
        response["Cache-Control"] = "public, max-age=86400"
        return response
