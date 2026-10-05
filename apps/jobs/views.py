from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.core.pagination import PerPageMixin
from apps.crm.hub import TasksHubMixin
from apps.users.roles import (
    ALL_ROLES,
    OWNER_ONLY,
    SALES_ROLES,
    OwnerRequiredMixin,
    Role,
    RoleRequiredMixin,
    SalesRoleRequiredMixin,
    user_role,
)

from . import reports
from .access import invoices_for, jobs_for, quotes_for
from .calendar import DEFAULT_VIEW, VIEWS, calendar_days, calendar_range
from .forms import JobForm, JobLineFormSet, QuoteForm, QuoteLineFormSet, ServiceTypeForm
from .models import Job, JobAssignment, Quote, ServiceType

User = get_user_model()


class CalendarView(RoleRequiredMixin, TemplateView):
    """Day / week / month schedule. Every role may open it; what it
    shows is scoped by jobs_for() (a cleaner sees their own jobs)."""

    allowed_roles = ALL_ROLES
    template_name = "jobs/calendar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET
        today = timezone.localdate()
        view = params.get("view") if params.get("view") in VIEWS else DEFAULT_VIEW
        cal = calendar_range(view, _parse_day(params.get("date")) or today)

        crew_id = None
        crew_members = []
        if user_role(self.request.user) in SALES_ROLES:
            crew_members = User.objects.filter(
                is_active=True, groups__name=Role.CLEANER.value
            ).order_by("first_name", "last_name", "username")
            requested = params.get("crew", "")
            if requested.isdigit() and any(m.pk == int(requested) for m in crew_members):
                crew_id = int(requested)

        can_schedule = user_role(self.request.user) in SALES_ROLES
        days = calendar_days(self.request.user, cal, crew_id=crew_id, today=today)
        for day in days:
            day["url"] = calendar_url("day", day["date"], crew_id)
        context.update(
            cal=cal,
            view_links=[
                (name.title(), calendar_url(name, cal.anchor, crew_id), name == view)
                for name in VIEWS
            ],
            previous_url=calendar_url(view, cal.previous, crew_id),
            next_url=calendar_url(view, cal.next, crew_id),
            today_url=calendar_url(view, today, crew_id),
            today=today,
            days=days,
            weeks=[days[i : i + 7] for i in range(0, len(days), 7)],
            has_events=any(day["events"] for day in days),
            crew_members=crew_members,
            crew_id=crew_id,
            can_schedule=can_schedule,
            new_job_url=reverse("jobs:job_create") if can_schedule else "",
            new_job_label="Schedule a job",
        )
        return context


class JobDetailView(RoleRequiredMixin, DetailView):
    """Anyone who can see the job (jobs_for) — others get a 404, never a
    403, so a job's existence isn't revealed. Prices are for sales roles;
    invoices for the Owner."""

    allowed_roles = ALL_ROLES
    template_name = "jobs/job_detail.html"
    context_object_name = "job"

    def get_queryset(self):
        return (
            jobs_for(self.request.user)
            .with_totals()
            .select_related("contact", "service_property", "primary_service_type", "quote")
            .select_related("sales_rep")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        job = self.object
        role = user_role(self.request.user)
        context.update(
            is_sales=role in SALES_ROLES,
            line_items=job.line_items.select_related("service_type"),
            assignments=job.assignments.select_related("user").order_by("user__first_name"),
            job_notes=job.note_set.select_related("author"),
            invoices=invoices_for(self.request.user).filter(job=job).with_balances(),
            today=timezone.localdate(),
            is_owner=role in OWNER_ONLY,
        )
        return context


class JobFormMixin(SalesRoleRequiredMixin, PermissionRequiredMixin):
    """Booking and moving jobs — the Owner and Sales Reps. A Cleaner sees
    their schedule but doesn't set it (ADR 0008).

    The crew and the line items are saved in one transaction with the
    job, so a half-booked job can't survive a failure partway through.
    """

    model = Job
    form_class = JobForm
    template_name = "jobs/job_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "lines" not in context:
            context["lines"] = JobLineFormSet(
                self.request.POST or None, instance=self.object, prefix="lines"
            )
        return context

    def form_valid(self, form):
        lines = JobLineFormSet(self.request.POST, instance=form.instance, prefix="lines")
        # The formset needs the job's primary key, so validate it against
        # an unsaved instance first and only commit once both are good.
        if not lines.is_valid():
            return self.render_to_response(self.get_context_data(form=form, lines=lines))
        with transaction.atomic():
            if not form.instance.pk:
                form.instance.created_by = self.request.user
            _stamp_completion(form.instance)
            self.object = form.save()
            lines.instance = self.object
            lines.save()
            self._save_crew(form.cleaned_data["crew"])
        messages.success(self.request, self.success_message % {"number": self.object.number})
        return redirect(self.object.get_absolute_url())

    def _save_crew(self, crew):
        """Add and remove assignments rather than replacing them, so
        hours already logged against a crew member survive an edit."""
        wanted = {member.pk for member in crew}
        existing = {a.user_id: a for a in self.object.assignments.all()}
        for user_id, assignment in existing.items():
            if user_id not in wanted:
                assignment.delete()
        for user_id in wanted - set(existing):
            JobAssignment.objects.create(job=self.object, user_id=user_id)


def _stamp_completion(job):
    """Record when a job was finished, from its status.

    Every count of finished work — the dashboard, the monthly goal,
    Financials, a cleaner's week — is by `completed_at`, not by status,
    so a job marked done without a date would say "Completed" on screen
    and be counted nowhere. Re-opening one clears the date again.
    """
    if job.status == Job.Status.COMPLETED:
        if job.completed_at is None:
            job.completed_at = timezone.now()
    else:
        job.completed_at = None


class JobCreateView(JobFormMixin, CreateView):
    permission_required = "jobs.add_job"
    success_message = "Scheduled %(number)s."

    def get_initial(self):
        initial = super().get_initial()
        initial.setdefault("sales_rep", self.request.user.pk)
        contact = self.request.GET.get("contact", "")
        if contact.isdigit():
            initial.setdefault("contact", int(contact))
        start = _parse_day(self.request.GET.get("date"))
        if start:
            # Arriving from a day on the schedule: start that morning.
            begins = timezone.make_aware(datetime.combine(start, time(9)))
            initial.setdefault("scheduled_start", begins)
            initial.setdefault("scheduled_end", begins + timedelta(hours=2))
        return initial


class JobUpdateView(JobFormMixin, UpdateView):
    permission_required = "jobs.change_job"
    success_message = "Updated %(number)s."

    def get_queryset(self):
        # Scoped like the detail page: out of scope is a 404, not a 403.
        return jobs_for(self.request.user)


QUOTE_FILTERS = {"open": Quote.OPEN_STATUSES, **{v: (v,) for v in Quote.Status.values}}


class QuoteListView(TasksHubMixin, SalesRoleRequiredMixin, PerPageMixin, ListView):
    """Estimates — open (draft or sent) by default. It keeps the Tasks
    hub's tabs, because it's one of them, under its own heading."""

    hub_tab = "quotes"
    template_name = "jobs/quote_list.html"
    context_object_name = "quotes"
    paginate_by = 25

    def get_queryset(self):
        params = self.request.GET
        queryset = (
            quotes_for(self.request.user).with_totals().select_related("contact", "prepared_by")
        )
        status = self._status()
        if status != "all":
            queryset = queryset.filter(status__in=QUOTE_FILTERS[status])
        if params.get("mine") == "1":
            queryset = queryset.filter(prepared_by=self.request.user)
        return queryset.order_by("-created_at", "-pk")

    def _status(self):
        """The status filter; anything unrecognized means "open"."""
        status = self.request.GET.get("status", "open")
        return status if status in QUOTE_FILTERS or status == "all" else "open"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status"] = self._status()
        context["status_choices"] = [("open", "Open"), *Quote.Status.choices, ("all", "All")]
        context["mine"] = self.request.GET.get("mine") == "1"
        context["new_quote_url"] = reverse("jobs:quote_create")
        return context


class QuoteDetailView(SalesRoleRequiredMixin, DetailView):
    template_name = "jobs/quote_detail.html"
    context_object_name = "quote"

    def get_queryset(self):
        return (
            quotes_for(self.request.user)
            .with_totals()
            .select_related("contact", "service_property", "prepared_by")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["line_items"] = self.object.line_items.select_related("service_type")
        context["jobs"] = self.object.jobs.select_related("primary_service_type")
        return context


class QuoteFormMixin(SalesRoleRequiredMixin, PermissionRequiredMixin):
    """Writing an estimate. Its lines are saved in the same transaction,
    and the dates that record what happened to it — sent, accepted — are
    stamped here rather than typed, so they always match the status."""

    model = Quote
    form_class = QuoteForm
    template_name = "jobs/quote_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "lines" not in context:
            context["lines"] = QuoteLineFormSet(
                self.request.POST or None, instance=self.object, prefix="lines"
            )
        return context

    def form_valid(self, form):
        lines = QuoteLineFormSet(self.request.POST, instance=form.instance, prefix="lines")
        if not lines.is_valid():
            return self.render_to_response(self.get_context_data(form=form, lines=lines))
        with transaction.atomic():
            if not form.instance.pk:
                form.instance.prepared_by = self.request.user
            _stamp_status(form.instance)
            self.object = form.save()
            lines.instance = self.object
            lines.save()
        messages.success(self.request, self.success_message % {"number": self.object.number})
        return redirect(self.object.get_absolute_url())


def _stamp_status(quote):
    """Record when an estimate went out and when it was taken up.

    `sent_at` is set once and kept: an estimate re-sent after a
    correction keeps the date the customer first saw it, which is what
    the expiry counts from. `accepted_at` follows the status instead, so
    one that's since been declined doesn't still show a day it was won.
    """
    if quote.status != Quote.Status.DRAFT and quote.sent_at is None:
        quote.sent_at = timezone.now()
    if quote.status != Quote.Status.ACCEPTED:
        quote.accepted_at = None
    elif quote.accepted_at is None:
        quote.accepted_at = timezone.now()


class QuoteCreateView(QuoteFormMixin, CreateView):
    permission_required = "jobs.add_quote"
    success_message = "Created %(number)s."

    def get_initial(self):
        initial = super().get_initial()
        contact = self.request.GET.get("contact", "")
        if contact.isdigit():
            initial.setdefault("contact", int(contact))
        return initial


class QuoteUpdateView(QuoteFormMixin, UpdateView):
    permission_required = "jobs.change_quote"
    success_message = "Updated %(number)s."

    def get_queryset(self):
        return quotes_for(self.request.user)


class FinancialsView(OwnerRequiredMixin, TemplateView):
    """Owner-only money page: revenue, collected, expenses and net for a
    period; revenue by service and rep; expenses by category; what's
    still owed and how late. Definitions live in apps/jobs/reports.py."""

    template_name = "jobs/financials.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET
        today = timezone.localdate()
        period, error = reports.report_period(
            params.get("range", "month"),
            _parse_day(params.get("start")),
            _parse_day(params.get("end")),
            today,
        )
        summary = reports.summary(period)
        kind, buckets = reports.trend(period)
        context.update(
            period=period,
            period_error=error,
            presets=[(key, label, key == period.preset) for key, label in reports.PRESETS.items()],
            today=today,
            summary=summary,
            by_service=reports.revenue_by_service(period, summary["revenue"]),
            by_rep=reports.revenue_by_rep(period, summary["revenue"]),
            by_category=reports.expenses_by_category(period, summary["expenses"]),
            aging=reports.aging(today),
            outstanding=reports.outstanding(),
            oldest_unpaid=reports.oldest_unpaid(),
            chart=reports.chart_bars(kind, buckets) if len(buckets) > 1 else None,
        )
        return context


class ServiceListView(OwnerRequiredMixin, ListView):
    """The service catalog — prices, follow-up intervals, calendar
    colors. Owner-only (ADR 0008)."""

    model = ServiceType
    template_name = "jobs/service_list.html"
    context_object_name = "services"


class ServiceUpdateView(OwnerRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = ServiceType
    form_class = ServiceTypeForm
    template_name = "jobs/service_form.html"
    context_object_name = "service"
    permission_required = "jobs.change_servicetype"
    success_url = reverse_lazy("jobs:service_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Updated “{self.object.name}”.")
        return response


def _parse_day(value):
    """A YYYY-MM-DD query value, or None if missing or not a real date."""
    try:
        return parse_date(value or "")
    except ValueError:  # well-formed but impossible, e.g. 2026-02-30
        return None


def calendar_url(view, day, crew_id=None):
    """Link to a calendar view/date, keeping the crew filter."""
    url = f"{reverse('jobs:calendar')}?view={view}&date={day.isoformat()}"
    return f"{url}&crew={crew_id}" if crew_id else url
