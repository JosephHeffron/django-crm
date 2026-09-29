import json
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.db.models import Count, F, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.crm.models import Activity, Company, Contact, Deal, Lead, Task
from apps.jobs.access import jobs_for, quotes_for
from apps.jobs.calendar import day_bounds
from apps.jobs.models import Job, JobAssignment, Quote
from apps.jobs.reports import invoiced_revenue, outstanding
from apps.messaging.services import unread_count
from apps.users.roles import Role, SalesRoleRequiredMixin, user_role

from . import pwa

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
    """Role-aware at-a-glance page (ADR 0008): today's jobs and unread
    messages for everyone; quotes, follow-ups, site visits, tasks and
    recent activity for sales roles; revenue for the Owner; a cleaner's
    own schedule and hours. Every figure is a plain ORM aggregate,
    scoped through apps/jobs/access.py.
    """

    template_name = "core/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        role = user_role(user)
        context["role"] = role
        if role is None:
            return context

        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        day_start, day_end = day_bounds(today, today)
        jobs = jobs_for(user).exclude(status=Job.Status.CANCELLED)
        context["today"] = today
        todays_jobs = jobs.filter(scheduled_start__gte=day_start, scheduled_start__lt=day_end)
        context["todays_job_count"] = todays_jobs.count()
        context["todays_jobs"] = (
            todays_jobs.select_related("contact", "service_property", "primary_service_type")
            .prefetch_related("crew")
            .order_by("scheduled_start", "pk")[:DASHBOARD_LIST_LIMIT]
        )
        context["unread_messages"] = unread_count(user)

        if role == Role.CLEANER:
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
            context["jobs_done_this_week"] = week.count()
            context["hours_this_week"] = week.aggregate(total=Sum("hours_worked"))["total"] or 0
            return context

        # Owner sees the whole business; a Sales Rep sees their own pipeline.
        is_owner = role == Role.OWNER
        open_quotes = quotes_for(user).filter(status__in=[Quote.Status.DRAFT, Quote.Status.SENT])
        follow_ups = Task.objects.filter(kind=Task.Kind.FOLLOW_UP, status=Task.Status.PENDING)
        visit_start, visit_end = day_bounds(today, today + timedelta(days=VISIT_DAYS - 1))
        visits = quotes_for(user).filter(
            site_visit_at__gte=visit_start,
            site_visit_at__lt=visit_end,
            status__in=[Quote.Status.DRAFT, Quote.Status.SENT],
        )
        if not is_owner:
            open_quotes = open_quotes.filter(prepared_by=user)
            follow_ups = follow_ups.filter(assigned_to=user)
            visits = visits.filter(prepared_by=user)

        context["is_owner"] = is_owner
        context["open_quotes"] = open_quotes.with_totals().aggregate(
            count=Count("pk"), total=Sum("total_amount")
        )
        context["follow_ups_due"] = follow_ups.filter(due_date__lte=today).count()
        context["follow_ups_overdue"] = follow_ups.filter(due_date__lt=today).count()
        context["site_visits"] = visits.select_related("contact", "service_property").order_by(
            "site_visit_at", "pk"
        )[:DASHBOARD_LIST_LIMIT]
        if is_owner:
            context["revenue_today"] = invoiced_revenue(today, today)
            context["revenue_week"] = invoiced_revenue(week_start, today)
            context["outstanding"] = outstanding()

        context["my_tasks"] = (
            Task.objects.filter(assigned_to=user, status=Task.Status.PENDING)
            .select_related("contact", "service_type")
            .order_by(F("due_date").asc(nulls_last=True), "pk")[:DASHBOARD_LIST_LIMIT]
        )
        context["recent_activities"] = Activity.objects.select_related(
            "created_by", "company", "contact"
        )[:DASHBOARD_LIST_LIMIT]
        return context


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
    }


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
        return JsonResponse(pwa.manifest(), content_type="application/manifest+json")


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
