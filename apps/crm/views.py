from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import (
    ActivityForm,
    CompanyForm,
    ContactForm,
    DealForm,
    LeadConversionForm,
    LeadForm,
    TaskForm,
)
from .models import Activity, AuditLogEntry, Company, Contact, Deal, Lead, Task


def _split_lead_name(name):
    parts = name.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return name.strip(), ""


def _int_or_none(value):
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _log_activity_url(field, obj):
    return f"{reverse('crm:activity_create')}?{field}={obj.pk}"


def _sync_deal_closed_at(deal):
    """Keep closed_at consistent with stage — set when a deal reaches a
    closed stage, cleared if it's reopened. Documented in
    docs/DATABASE_DESIGN.md's Lifecycle behavior as an application-layer
    invariant (no DB constraint enforces it), so this is where it
    actually gets enforced, on every create/update.
    """
    if deal.stage in Deal.CLOSED_STAGES:
        if deal.closed_at is None:
            deal.closed_at = timezone.now()
    else:
        deal.closed_at = None


def _sync_task_completed_at(task):
    """Same pattern as _sync_deal_closed_at, for Task.completed_at —
    set when status becomes completed, cleared otherwise (reopened to
    pending, or cancelled). Documented in docs/DATABASE_DESIGN.md's
    Lifecycle behavior as an application-layer invariant.
    """
    if task.status == Task.Status.COMPLETED:
        if task.completed_at is None:
            task.completed_at = timezone.now()
    else:
        task.completed_at = None


def _record_audit_log(user, obj, action, changes=None):
    """Write one AuditLogEntry for a Company/Contact/Lead/Deal change.

    Called explicitly from each audited model's Create/UpdateView —
    see docs/DATABASE_DESIGN.md's "Audit history" section for why this
    isn't signal-based.
    """
    AuditLogEntry.objects.create(
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        user=user,
        action=action,
        changes=changes or {},
    )


def _diff_changed_fields(previous, current, changed_fields):
    """Build the {field: [old, new]} dict AuditLogEntry.changes expects,
    from the pre-edit instance, the post-edit instance, and the list of
    field names the form actually changed (form.changed_data).
    """
    changes = {}
    for field in changed_fields:
        old_value = getattr(previous, field, None)
        new_value = getattr(current, field, None)
        changes[field] = [
            None if old_value is None else str(old_value),
            None if new_value is None else str(new_value),
        ]
    return changes


def _audit_log_for(obj):
    return AuditLogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk
    ).select_related("user")


class CompanyListView(LoginRequiredMixin, ListView):
    model = Company
    template_name = "crm/company_list.html"
    context_object_name = "companies"
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(name__icontains=query)

        status = self.request.GET.get("status")
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["status"] = self.request.GET.get("status", "")
        return context


class CompanyDetailView(LoginRequiredMixin, DetailView):
    model = Company
    template_name = "crm/company_detail.html"
    context_object_name = "company"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["contacts"] = self.object.contacts.all()
        context["deals"] = self.object.deals.all()
        context["activities"] = self.object.activities.all()
        context["log_activity_url"] = _log_activity_url("company", self.object)
        context["audit_log"] = _audit_log_for(self.object)
        return context


class CompanyCreateView(LoginRequiredMixin, CreateView):
    model = Company
    form_class = CompanyForm
    template_name = "crm/company_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        _record_audit_log(self.request.user, self.object, AuditLogEntry.Action.CREATED)
        messages.success(self.request, f"Created company “{self.object.name}”.")
        return response


class CompanyUpdateView(LoginRequiredMixin, UpdateView):
    model = Company
    form_class = CompanyForm
    template_name = "crm/company_form.html"

    def form_valid(self, form):
        previous = Company.objects.get(pk=self.object.pk)
        response = super().form_valid(form)
        changes = _diff_changed_fields(previous, self.object, form.changed_data)
        if changes:
            _record_audit_log(self.request.user, self.object, AuditLogEntry.Action.UPDATED, changes)
        messages.success(self.request, f"Updated company “{self.object.name}”.")
        return response


class CompanyDeactivateView(LoginRequiredMixin, DetailView):
    """GET shows a confirmation page; POST deactivates (is_active=False).

    Not a DeleteView: docs/DATABASE_DESIGN.md documents `is_active` as
    the soft-removal mechanism — "companies are never hard-deleted from
    the UI" — so this never calls .delete(). (Hard deletion is still
    possible for a superuser via the Django admin, just not exposed
    here.) A side benefit: deactivation never touches Deal.company's
    on_delete=PROTECT constraint, so there's no failure mode to handle
    the way an actual delete would have.
    """

    model = Company
    template_name = "crm/company_confirm_deactivate.html"

    def post(self, request, *args, **kwargs):
        company = self.get_object()
        was_active = company.is_active
        company.is_active = False
        company.save(update_fields=["is_active"])
        if was_active != company.is_active:
            _record_audit_log(
                request.user,
                company,
                AuditLogEntry.Action.UPDATED,
                {"is_active": [str(was_active), str(company.is_active)]},
            )
        messages.success(request, f"Deactivated company “{company.name}”.")
        return redirect(company.get_absolute_url())


class ContactListView(LoginRequiredMixin, ListView):
    model = Contact
    template_name = "crm/contact_list.html"
    context_object_name = "contacts"
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset().select_related("company")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )

        status = self.request.GET.get("status")
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)

        company_id = self.request.GET.get("company")
        if company_id:
            try:
                company_id = int(company_id)
            except ValueError:
                pass
            else:
                queryset = queryset.filter(company_id=company_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["status"] = self.request.GET.get("status", "")
        context["company_id"] = self.request.GET.get("company", "")
        context["companies"] = Company.objects.order_by("name")
        return context


class ContactDetailView(LoginRequiredMixin, DetailView):
    model = Contact
    template_name = "crm/contact_detail.html"
    context_object_name = "contact"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["deals"] = self.object.deals.all()
        context["tasks"] = self.object.tasks.all()
        context["activities"] = self.object.activities.all()
        context["log_activity_url"] = _log_activity_url("contact", self.object)
        context["audit_log"] = _audit_log_for(self.object)
        return context


class ContactCreateView(LoginRequiredMixin, CreateView):
    model = Contact
    form_class = ContactForm
    template_name = "crm/contact_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        _record_audit_log(self.request.user, self.object, AuditLogEntry.Action.CREATED)
        messages.success(self.request, f"Created contact “{self.object}”.")
        return response


class ContactUpdateView(LoginRequiredMixin, UpdateView):
    model = Contact
    form_class = ContactForm
    template_name = "crm/contact_form.html"

    def form_valid(self, form):
        previous = Contact.objects.get(pk=self.object.pk)
        response = super().form_valid(form)
        changes = _diff_changed_fields(previous, self.object, form.changed_data)
        if changes:
            _record_audit_log(self.request.user, self.object, AuditLogEntry.Action.UPDATED, changes)
        messages.success(self.request, f"Updated contact “{self.object}”.")
        return response


class ContactDeactivateView(LoginRequiredMixin, DetailView):
    """Same pattern as CompanyDeactivateView — is_active=False, never a
    hard delete. See that view's docstring for the reasoning."""

    model = Contact
    template_name = "crm/contact_confirm_deactivate.html"

    def post(self, request, *args, **kwargs):
        contact = self.get_object()
        was_active = contact.is_active
        contact.is_active = False
        contact.save(update_fields=["is_active"])
        if was_active != contact.is_active:
            _record_audit_log(
                request.user,
                contact,
                AuditLogEntry.Action.UPDATED,
                {"is_active": [str(was_active), str(contact.is_active)]},
            )
        messages.success(request, f"Deactivated contact “{contact}”.")
        return redirect(contact.get_absolute_url())


class LeadListView(LoginRequiredMixin, ListView):
    model = Lead
    template_name = "crm/lead_list.html"
    context_object_name = "leads"
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(company_name__icontains=query)
                | Q(email__icontains=query)
            )

        status = self.request.GET.get("status")
        if status in Lead.Status.values:
            queryset = queryset.filter(status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["status"] = self.request.GET.get("status", "")
        context["status_choices"] = Lead.Status.choices
        return context


class LeadDetailView(LoginRequiredMixin, DetailView):
    model = Lead
    template_name = "crm/lead_detail.html"
    context_object_name = "lead"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["activities"] = self.object.activities.all()
        context["log_activity_url"] = _log_activity_url("lead", self.object)
        context["audit_log"] = _audit_log_for(self.object)
        return context


class LeadCreateView(LoginRequiredMixin, CreateView):
    model = Lead
    form_class = LeadForm
    template_name = "crm/lead_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        _record_audit_log(self.request.user, self.object, AuditLogEntry.Action.CREATED)
        messages.success(self.request, f"Created lead “{self.object.name}”.")
        return response


class LeadUpdateView(LoginRequiredMixin, UpdateView):
    model = Lead
    form_class = LeadForm
    template_name = "crm/lead_form.html"

    def form_valid(self, form):
        previous = Lead.objects.get(pk=self.object.pk)
        response = super().form_valid(form)
        changes = _diff_changed_fields(previous, self.object, form.changed_data)
        if changes:
            _record_audit_log(self.request.user, self.object, AuditLogEntry.Action.UPDATED, changes)
        messages.success(self.request, f"Updated lead “{self.object.name}”.")
        return response


class LeadConvertView(LoginRequiredMixin, View):
    """GET shows a conversion form pre-filled from the Lead; POST
    creates/links a Company, always creates a Contact, optionally opens
    a Deal, then marks the Lead converted — the workflow documented in
    docs/DATABASE_DESIGN.md's Lifecycle behavior section. The Lead row
    is kept, not deleted, as the historical record of where the
    Company/Contact/Deal came from.
    """

    template_name = "crm/lead_convert.html"

    def get(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk)
        if lead.status == Lead.Status.CONVERTED:
            messages.info(request, f"“{lead.name}” has already been converted.")
            return redirect(lead.get_absolute_url())

        first_name, last_name = _split_lead_name(lead.name)
        form = LeadConversionForm(
            initial={
                "new_company_name": lead.company_name,
                "contact_first_name": first_name,
                "contact_last_name": last_name,
                "contact_email": lead.email,
                "contact_phone": lead.phone,
                "deal_title": f"{lead.name} deal",
            }
        )
        return render(request, self.template_name, {"lead": lead, "form": form})

    def post(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk)
        if lead.status == Lead.Status.CONVERTED:
            messages.info(request, f"“{lead.name}” has already been converted.")
            return redirect(lead.get_absolute_url())

        form = LeadConversionForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"lead": lead, "form": form})

        data = form.cleaned_data
        if data["existing_company"]:
            company = data["existing_company"]
        elif data["new_company_name"]:
            company = Company.objects.create(name=data["new_company_name"], created_by=request.user)
            _record_audit_log(request.user, company, AuditLogEntry.Action.CREATED)
        else:
            company = None

        contact = Contact.objects.create(
            first_name=data["contact_first_name"],
            last_name=data["contact_last_name"],
            email=data["contact_email"],
            phone=data["contact_phone"],
            company=company,
            created_by=request.user,
        )
        _record_audit_log(request.user, contact, AuditLogEntry.Action.CREATED)

        deal = None
        if data["create_deal"]:
            deal = Deal.objects.create(
                title=data["deal_title"],
                company=company,
                contact=contact,
                value=data["deal_value"],
                created_by=request.user,
            )
            _record_audit_log(request.user, deal, AuditLogEntry.Action.CREATED)

        # Conversion's own record-level changes are logged as a normal
        # "updated" entry on the Lead (docs/DATABASE_DESIGN.md's Audit
        # history section) — there's no special-cased "conversion"
        # audit action.
        previous_status = lead.status
        lead.status = Lead.Status.CONVERTED
        lead.converted_at = timezone.now()
        lead.converted_company = company
        lead.converted_contact = contact
        lead.converted_deal = deal
        lead.save(
            update_fields=[
                "status",
                "converted_at",
                "converted_company",
                "converted_contact",
                "converted_deal",
                "updated_at",
            ]
        )
        _record_audit_log(
            request.user,
            lead,
            AuditLogEntry.Action.UPDATED,
            {"status": [previous_status, lead.status]},
        )

        messages.success(request, f"Converted “{lead.name}”.")
        return redirect(lead.get_absolute_url())


class DealListView(LoginRequiredMixin, ListView):
    model = Deal
    template_name = "crm/deal_list.html"
    context_object_name = "deals"
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset().select_related("company", "contact")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(title__icontains=query)

        stage = self.request.GET.get("stage")
        if stage in Deal.Stage.values:
            queryset = queryset.filter(stage=stage)

        open_only = self.request.GET.get("open") == "1"
        if open_only:
            queryset = queryset.exclude(stage__in=Deal.CLOSED_STAGES)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["stage"] = self.request.GET.get("stage", "")
        context["open_only"] = self.request.GET.get("open") == "1"
        context["stage_choices"] = Deal.Stage.choices
        return context


class DealDetailView(LoginRequiredMixin, DetailView):
    model = Deal
    template_name = "crm/deal_detail.html"
    context_object_name = "deal"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tasks"] = self.object.tasks.all()
        context["activities"] = self.object.activities.all()
        context["log_activity_url"] = _log_activity_url("deal", self.object)
        context["audit_log"] = _audit_log_for(self.object)
        return context


class DealCreateView(LoginRequiredMixin, CreateView):
    model = Deal
    form_class = DealForm
    template_name = "crm/deal_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        _sync_deal_closed_at(form.instance)
        response = super().form_valid(form)
        _record_audit_log(self.request.user, self.object, AuditLogEntry.Action.CREATED)
        messages.success(self.request, f"Created deal “{self.object.title}”.")
        return response


class DealUpdateView(LoginRequiredMixin, UpdateView):
    model = Deal
    form_class = DealForm
    template_name = "crm/deal_form.html"

    def form_valid(self, form):
        previous = Deal.objects.get(pk=self.object.pk)
        _sync_deal_closed_at(form.instance)
        response = super().form_valid(form)
        changes = _diff_changed_fields(previous, self.object, form.changed_data)
        if changes:
            _record_audit_log(self.request.user, self.object, AuditLogEntry.Action.UPDATED, changes)
        messages.success(self.request, f"Updated deal “{self.object.title}”.")
        return response


class ActivityListView(LoginRequiredMixin, ListView):
    model = Activity
    template_name = "crm/activity_list.html"
    context_object_name = "activities"
    paginate_by = 25

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("company", "contact", "lead", "deal", "created_by")
        )
        activity_type = self.request.GET.get("type")
        if activity_type in Activity.ActivityType.values:
            queryset = queryset.filter(activity_type=activity_type)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["activity_type"] = self.request.GET.get("type", "")
        context["type_choices"] = Activity.ActivityType.choices
        return context


class ActivityCreateView(LoginRequiredMixin, CreateView):
    """No ActivityUpdateView exists, deliberately — Activity.save()
    itself rejects updates (docs/DATABASE_DESIGN.md, immutable history).
    No ActivityDetailView either: an Activity's "detail page" is the
    timeline on whichever Company/Contact/Lead/Deal it's attached to.
    """

    model = Activity
    form_class = ActivityForm
    template_name = "crm/activity_form.html"

    def get_initial(self):
        # Supports linking in from a specific record's detail page
        # (e.g. "Log a call" on a Company) via ?company=<id> etc., so
        # the relevant relation is pre-selected rather than making the
        # user pick it again.
        initial = super().get_initial()
        for field in ("company", "contact", "lead", "deal"):
            value = _int_or_none(self.request.GET.get(field))
            if value is not None:
                initial[field] = value
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "Logged activity.")
        return response

    def get_success_url(self):
        activity = self.object
        for related in (activity.company, activity.contact, activity.lead, activity.deal):
            if related is not None:
                return related.get_absolute_url()
        return reverse("crm:activity_list")


class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = "crm/task_list.html"
    context_object_name = "tasks"
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset().select_related("assigned_to", "contact", "deal")

        status = self.request.GET.get("status")
        if status in Task.Status.values:
            queryset = queryset.filter(status=status)

        priority = self.request.GET.get("priority")
        if priority in Task.Priority.values:
            queryset = queryset.filter(priority=priority)

        if self.request.GET.get("mine") == "1":
            queryset = queryset.filter(assigned_to=self.request.user)

        if self.request.GET.get("overdue") == "1":
            queryset = queryset.filter(
                status=Task.Status.PENDING, due_date__lt=timezone.localdate()
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status"] = self.request.GET.get("status", "")
        context["priority"] = self.request.GET.get("priority", "")
        context["mine"] = self.request.GET.get("mine") == "1"
        context["overdue"] = self.request.GET.get("overdue") == "1"
        context["status_choices"] = Task.Status.choices
        context["priority_choices"] = Task.Priority.choices
        return context


class TaskDetailView(LoginRequiredMixin, DetailView):
    model = Task
    template_name = "crm/task_detail.html"
    context_object_name = "task"


class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "crm/task_form.html"

    def get_initial(self):
        initial = super().get_initial()
        initial.setdefault("assigned_to", self.request.user.pk)
        for field in ("contact", "deal"):
            value = _int_or_none(self.request.GET.get(field))
            if value is not None:
                initial[field] = value
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        _sync_task_completed_at(form.instance)
        response = super().form_valid(form)
        messages.success(self.request, f"Created task “{self.object.title}”.")
        return response


class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "crm/task_form.html"

    def form_valid(self, form):
        _sync_task_completed_at(form.instance)
        response = super().form_valid(form)
        messages.success(self.request, f"Updated task “{self.object.title}”.")
        return response


class TaskCompleteView(LoginRequiredMixin, View):
    """One-click completion from the list or detail page, without going
    through the full edit form — the dedicated "completion workflow"
    the roadmap calls for, separate from ordinary editing. POST only.

    Only acts on a pending task. The template only renders this action
    for pending tasks, but that's a UI-level guard only — without this
    check here too, a direct POST (e.g. a stale page, or the endpoint
    hit directly) could silently revive an already-cancelled task
    straight to completed. Same shape as LeadConvertView's "already
    converted" guard.
    """

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        if task.status != Task.Status.PENDING:
            messages.info(request, f"“{task.title}” is not pending and was left unchanged.")
            return redirect(task.get_absolute_url())

        task.status = Task.Status.COMPLETED
        _sync_task_completed_at(task)
        task.save(update_fields=["status", "completed_at", "updated_at"])
        messages.success(request, f"Completed “{task.title}”.")

        next_url = request.POST.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect(task.get_absolute_url())
