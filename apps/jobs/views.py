from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.core.pagination import PerPageMixin
from apps.core.templatetags.crm_format import money
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
from .forms import (
    ExpenseForm,
    InvoiceForm,
    InvoiceLineFormSet,
    JobForm,
    JobLineFormSet,
    PaymentForm,
    QuoteForm,
    QuoteLineFormSet,
    ServiceTypeForm,
    line_formset,
)
from .models import (
    TOTAL_FIELD,
    ZERO,
    Expense,
    Invoice,
    InvoiceLineItem,
    Job,
    JobAssignment,
    Payment,
    Quote,
    ServiceType,
)

User = get_user_model()

# How long a new invoice is given to be paid, unless the date is changed.
INVOICE_TERMS_DAYS = 14


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


class InvoiceListView(OwnerRequiredMixin, PerPageMixin, ListView):
    """Every invoice, filtered by where its money stands. Paid and
    overdue aren't stored — they follow from the payments and the due
    date (apps/jobs/reports.py)."""

    template_name = "jobs/invoice_list.html"
    context_object_name = "invoices"

    def filter_key(self):
        key = self.request.GET.get("show", "unpaid")
        return key if key in reports.INVOICE_FILTERS else "unpaid"

    def get_queryset(self):
        return reports.filter_invoices(
            invoices_for(self.request.user)
            .with_balances()
            .select_related("contact", "job", "job__primary_service_type"),
            self.filter_key(),
            timezone.localdate(),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        key = self.filter_key()
        context.update(
            show=key,
            filters=[(k, label, k == key) for k, label in reports.INVOICE_FILTERS.items()],
            totals=reports.invoice_totals(self.get_queryset()),
            today=timezone.localdate(),
        )
        return context


class InvoiceDetailView(OwnerRequiredMixin, DetailView):
    template_name = "jobs/invoice_detail.html"
    context_object_name = "invoice"

    def get_queryset(self):
        return (
            invoices_for(self.request.user)
            .with_balances()
            .select_related("contact", "job", "job__primary_service_type")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            line_items=self.object.line_items.select_related("service_type"),
            payments=self.object.payments.select_related("recorded_by"),
            today=timezone.localdate(),
            payment_status=self.object.payment_status(timezone.localdate()),
        )
        return context


class InvoiceFormMixin(OwnerRequiredMixin, PermissionRequiredMixin):
    model = Invoice
    form_class = InvoiceForm
    template_name = "jobs/invoice_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "lines" not in context:
            initial = self.line_initial()
            # Sized to what it's seeded with: a formset renders `extra`
            # rows however many initial ones it's given, so billing a
            # three-line job would otherwise show one and quietly drop
            # the other two.
            formset = line_formset(
                Invoice, InvoiceLineItem, extra=len(initial) + 1 if initial else 1
            )
            context["lines"] = formset(
                self.request.POST or None,
                instance=self.object,
                prefix="lines",
                initial=initial,
            )
        return context

    def line_initial(self):
        return None

    def form_valid(self, form):
        lines = InvoiceLineFormSet(self.request.POST, instance=form.instance, prefix="lines")
        if not lines.is_valid():
            return self.render_to_response(self.get_context_data(form=form, lines=lines))
        with transaction.atomic():
            self.object = form.save()
            lines.instance = self.object
            lines.save()
        messages.success(self.request, self.success_message % {"number": self.object.number})
        return redirect(self.object.get_absolute_url())


class InvoiceCreateView(InvoiceFormMixin, CreateView):
    permission_required = "jobs.add_invoice"
    success_message = "Created %(number)s."

    def job(self):
        """The job this invoice is being raised for, if the page was
        opened from one."""
        pk = self.request.GET.get("job", "")
        if not pk.isdigit():
            return None
        return Job.objects.filter(pk=int(pk)).first()

    def get_initial(self):
        initial = super().get_initial()
        today = timezone.localdate()
        initial.setdefault("issued_on", today)
        initial.setdefault("due_on", today + timedelta(days=INVOICE_TERMS_DAYS))
        job = self.job()
        if job:
            initial.setdefault("job", job.pk)
        return initial

    def line_initial(self):
        """Opening from a job starts with that job's own lines, so the
        bill matches the work instead of being retyped."""
        job = self.job()
        if not job:
            return None
        return [
            {
                "service_type": line.service_type_id,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
            }
            for line in job.line_items.all()
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["from_job"] = self.job()
        return context


class InvoiceUpdateView(InvoiceFormMixin, UpdateView):
    permission_required = "jobs.change_invoice"
    success_message = "Updated %(number)s."

    def get_queryset(self):
        return invoices_for(self.request.user)


class PaymentCreateView(OwnerRequiredMixin, PermissionRequiredMixin, CreateView):
    """Money received against one invoice."""

    model = Payment
    form_class = PaymentForm
    template_name = "jobs/payment_form.html"
    permission_required = "jobs.add_payment"

    def invoice(self):
        return get_object_or_404(
            invoices_for(self.request.user).with_balances(), pk=self.kwargs["pk"]
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["invoice"] = self.invoice()
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        invoice = self.invoice()
        initial.setdefault("received_on", timezone.localdate())
        # The rest of the bill, which is what's usually being paid.
        # Quantized because the balance is a sum of sums and comes back
        # with more places than money has — a raw 300.0000 in a field
        # that steps in cents is one the browser refuses.
        if invoice.balance > 0:
            initial.setdefault("amount", invoice.balance.quantize(ZERO))
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["invoice"] = self.invoice()
        return context

    def form_valid(self, form):
        invoice = self.invoice()
        form.instance.invoice = invoice
        form.instance.recorded_by = self.request.user
        self.object = form.save()
        over = getattr(form, "overpayment", None)
        extra = f" That's {money(over)} more than the balance." if over else ""
        messages.success(
            self.request, f"Recorded {money(self.object.amount)} on {invoice.number}.{extra}"
        )
        return redirect(invoice.get_absolute_url())


class PaymentListView(OwnerRequiredMixin, PerPageMixin, ListView):
    """Everything received, newest first."""

    template_name = "jobs/payment_list.html"
    context_object_name = "payments"

    def get_queryset(self):
        return Payment.objects.select_related("invoice", "invoice__contact", "recorded_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total"] = self.get_queryset().aggregate(
            total=Coalesce(Sum("amount"), Value(ZERO), output_field=TOTAL_FIELD)
        )["total"]
        return context


class ExpenseListView(OwnerRequiredMixin, PerPageMixin, ListView):
    template_name = "jobs/expense_list.html"
    context_object_name = "expenses"

    def get_queryset(self):
        expenses = Expense.objects.select_related("recorded_by")
        category = self.request.GET.get("category", "")
        if category in Expense.Category.values:
            expenses = expenses.filter(category=category)
        return expenses

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.request.GET.get("category", "")
        context["category"] = category
        context["categories"] = Expense.Category.choices
        context["category_label"] = (
            Expense.Category(category).label if category in Expense.Category.values else ""
        )
        context["total"] = self.get_queryset().aggregate(
            total=Coalesce(Sum("amount"), Value(ZERO), output_field=TOTAL_FIELD)
        )["total"]
        return context


class ExpenseFormMixin(OwnerRequiredMixin, PermissionRequiredMixin):
    model = Expense
    form_class = ExpenseForm
    template_name = "jobs/expense_form.html"
    success_url = reverse_lazy("jobs:expense_list")

    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.recorded_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Saved {money(self.object.amount)} of expenses.")
        return response


class ExpenseCreateView(ExpenseFormMixin, CreateView):
    permission_required = "jobs.add_expense"

    def get_initial(self):
        initial = super().get_initial()
        initial.setdefault("date", timezone.localdate())
        return initial


class ExpenseUpdateView(ExpenseFormMixin, UpdateView):
    permission_required = "jobs.change_expense"


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
