from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Case, Count, F, Q, When
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core import redirects
from apps.core.models import Notification
from apps.core.notifications import notify
from apps.core.pagination import PerPageMixin
from apps.jobs.models import Job, Quote
from apps.users.roles import SalesRoleRequiredMixin

from . import audit
from .followups import record_completion
from .forms import (
    ActivityForm,
    BusinessPlanForm,
    ChecklistItemForm,
    CompanyForm,
    ContactForm,
    PropertyForm,
    TaskForm,
    contact_choices,
)
from .hub import TasksHubMixin
from .models import (
    Activity,
    AuditLogEntry,
    BusinessPlan,
    Company,
    Contact,
    Note,
    PlanChecklistItem,
    Property,
    Tag,
    Task,
)
from .timeline import contact_timeline, upcoming_jobs, with_last_dates


def _int_or_none(value):
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _log_activity_url(field, obj):
    return f"{reverse('crm:activity_create')}?{field}={obj.pk}"


def _sync_task_completed_at(task):
    """Keeps Task.completed_at in step with its status —
    set when status becomes completed, cleared otherwise (reopened to
    pending, or cancelled). Documented in docs/DATABASE_DESIGN.md's
    Lifecycle behavior as an application-layer invariant.
    """
    if task.status == Task.Status.COMPLETED:
        if task.completed_at is None:
            task.completed_at = timezone.now()
    else:
        task.completed_at = None
        task.completed_by = None


def _apply_task_completion(task, user, was_completed):
    """completed_at bookkeeping plus, on a transition *into* completed,
    record_completion() — who did it, and for a follow-up the contact
    touch that resets its clock (apps/crm/followups.py). Re-saving an
    already-completed task must not log a second touch."""
    _sync_task_completed_at(task)
    if task.status == Task.Status.COMPLETED and not was_completed:
        record_completion(task, user)


# Moved to apps/crm/audit.py in Phase 18.5 unit 5, when the change log
# widened past these four models. Aliased rather than rewritten at
# every call site, so the extraction reads as a pure move.
_record_audit_log = audit.record
_diff_changed_fields = audit.diff


def _audit_log_for(obj):
    return AuditLogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk
    ).select_related("user")


class CompanyListView(SalesRoleRequiredMixin, PerPageMixin, ListView):
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

        # A Company has no address of its own; its geography is where its
        # customers are. So it matches when ANY of them has an address
        # there. Nested subqueries rather than a two-hop join, for the
        # reason given on contacts_at().
        town, postal = address_filters(self.request.GET)
        if town or postal:
            queryset = queryset.filter(
                pk__in=Contact.objects.filter(pk__in=contacts_at(town, postal))
                .exclude(company__isnull=True)
                .values("company_id")
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["status"] = self.request.GET.get("status", "")
        context["town"], context["postal"] = address_filters(self.request.GET)
        context["towns"] = towns_on_record()
        return context


class CompanyDetailView(SalesRoleRequiredMixin, DetailView):
    model = Company
    template_name = "crm/company_detail.html"
    context_object_name = "company"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["contacts"] = self.object.contacts.all()
        context["activities"] = self.object.activities.all()
        context["log_activity_url"] = _log_activity_url("company", self.object)
        context["audit_log"] = _audit_log_for(self.object)
        return context


class CompanyCreateView(SalesRoleRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Company
    form_class = CompanyForm
    template_name = "crm/company_form.html"
    permission_required = "crm.add_company"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        _record_audit_log(self.request.user, self.object, AuditLogEntry.Action.CREATED)
        messages.success(self.request, f"Created company “{self.object.name}”.")
        return response


class CompanyUpdateView(SalesRoleRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Company
    form_class = CompanyForm
    template_name = "crm/company_form.html"
    permission_required = "crm.change_company"

    def form_valid(self, form):
        previous = Company.objects.get(pk=self.object.pk)
        response = super().form_valid(form)
        changes = _diff_changed_fields(previous, self.object, form.changed_data)
        if changes:
            _record_audit_log(self.request.user, self.object, AuditLogEntry.Action.UPDATED, changes)
        messages.success(self.request, f"Updated company “{self.object.name}”.")
        return response


class CompanyDeactivateView(SalesRoleRequiredMixin, PermissionRequiredMixin, DetailView):
    """GET shows a confirmation page; POST deactivates (is_active=False).

    Not a DeleteView: docs/DATABASE_DESIGN.md documents `is_active` as
    the soft-removal mechanism — "companies are never hard-deleted from
    the UI" — so this never calls .delete(). (Hard deletion is still
    possible for a superuser via the Django admin, just not exposed
    here.) A side benefit: deactivation never touches a company's
    on_delete=PROTECT constraint, so there's no failure mode to handle
    the way an actual delete would have.
    """

    model = Company
    template_name = "crm/company_confirm_deactivate.html"
    # Deactivation is a plain field change (docs/PERMISSIONS.md) —
    # no separate "deactivate" permission exists.
    permission_required = "crm.change_company"

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


CONTACT_SORTS = {
    "name": ("Name", ("last_name", "first_name", "pk")),
    "recent_job": ("Most recent job", (F("last_job_at").desc(nulls_last=True), "pk")),
    # Longest without a touch first: who's due a call.
    "last_contact": ("Longest since contact", (F("last_touch_at").asc(nulls_first=True), "pk")),
}


def contacts_at(town="", postal=""):
    """Contact ids with a service address in that town or postcode.

    Returned as a subquery for `pk__in`, never as a join. Joining
    `properties` would multiply the contact rows — a customer with a
    home and a rental in the same town matches twice — which corrupts
    both the rows shown and `paginator.count`, and still looks correct
    on page one. The tag filter below and `with_last_dates` follow the
    same discipline for the same reason.
    """
    addresses = Property.objects.all()
    if town:
        addresses = addresses.filter(city__iexact=town)
    if postal:
        addresses = addresses.filter(postal_code__iexact=postal)
    return addresses.values("contact_id")


def address_filters(params):
    """The town and postcode asked for, trimmed."""
    return params.get("town", "").strip(), params.get("postal", "").strip()


def towns_on_record():
    """Only towns somebody actually has an address in."""
    return (
        Property.objects.exclude(city="").order_by("city").values_list("city", flat=True).distinct()
    )


class ContactListView(SalesRoleRequiredMixin, PerPageMixin, ListView):
    model = Contact
    template_name = "crm/contact_list.html"
    context_object_name = "contacts"
    paginate_by = 25

    def get_queryset(self):
        params = self.request.GET
        queryset = with_last_dates(
            super().get_queryset().select_related("company", "owner").prefetch_related("tags")
        )
        query = params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
                | Q(phone__icontains=query)
            )

        status = params.get("status")
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)

        if params.get("stage") in Contact.Status.values:
            queryset = queryset.filter(status=params["stage"])

        company_id = _int_or_none(params.get("company"))
        if company_id is not None:
            queryset = queryset.filter(company_id=company_id)

        tag_id = _int_or_none(params.get("tag"))
        if tag_id is not None:
            queryset = queryset.filter(
                pk__in=Contact.tags.through.objects.filter(tag_id=tag_id).values("contact_id")
            )

        town, postal = address_filters(params)
        if town or postal:
            queryset = queryset.filter(pk__in=contacts_at(town, postal))

        _, ordering = CONTACT_SORTS.get(params.get("sort"), CONTACT_SORTS["name"])
        return queryset.order_by(*ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET
        context["query"] = params.get("q", "")
        context["status"] = params.get("status", "")
        context["stage"] = params.get("stage", "")
        context["company_id"] = params.get("company", "")
        context["tag_id"] = params.get("tag", "")
        context["sort"] = params.get("sort") if params.get("sort") in CONTACT_SORTS else "name"
        context["companies"] = Company.objects.order_by("name")
        context["tags"] = Tag.objects.order_by("name")
        context["stage_choices"] = Contact.Status.choices
        context["sort_choices"] = [(key, label) for key, (label, _) in CONTACT_SORTS.items()]
        context["town"], context["postal"] = address_filters(params)
        context["towns"] = towns_on_record()
        return context


class PropertyFormMixin(audit.AuditedFormMixin, SalesRoleRequiredMixin, PermissionRequiredMixin):
    """Create or correct a service address.

    Returns to wherever asked (`?next=`), handing back the new address
    so a half-filled job form can pick it up. Validated against this
    host, so the parameter cannot become an open redirect — a
    hand-rolled version of that check was a real bug in Phase 17.5.
    """

    model = Property
    form_class = PropertyForm
    template_name = "crm/property_form.html"

    def get_initial(self):
        initial = super().get_initial()
        contact_id = _int_or_none(self.request.GET.get("contact"))
        if contact_id is not None:
            initial.setdefault("contact", contact_id)
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["back"] = redirects.safe_next(self.request)
        return context

    def form_valid(self, form):
        # The demotion of a previous main address happens in the form's
        # own save(), because Django checks the constraint during
        # validation — before anything here could run.
        response = super().form_valid(form)
        messages.success(self.request, f"Saved {self.object}.")
        return response

    def get_success_url(self):
        target = redirects.safe_next(self.request)
        if target:
            # Hand the address back to whatever sent us here.
            return redirects.with_params(target, service_property=self.object.pk)
        return self.object.contact.get_absolute_url()


class PropertyCreateView(PropertyFormMixin, CreateView):
    permission_required = "crm.add_property"


class PropertyUpdateView(PropertyFormMixin, UpdateView):
    permission_required = "crm.change_property"


class ContactDetailView(SalesRoleRequiredMixin, DetailView):
    model = Contact
    template_name = "crm/contact_detail.html"
    context_object_name = "contact"

    def get_queryset(self):
        return with_last_dates(Contact.objects.select_related("company", "owner"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        contact = self.object
        context["properties"] = contact.properties.all()
        context["contact_tags"] = contact.tags.order_by("name")
        context["upcoming_jobs"] = upcoming_jobs(contact)
        context["jobs_completed"] = contact.jobs.filter(status=Job.Status.COMPLETED).count()
        context["open_quotes"] = contact.quotes.filter(status__in=Quote.OPEN_STATUSES).count()
        context["timeline"] = contact_timeline(contact, self.request.user)
        # Open tasks first, soonest due first.
        context["tasks"] = contact.tasks.select_related("assigned_to", "service_type").order_by(
            Case(When(status=Task.Status.PENDING, then=0), default=1),
            F("due_date").asc(nulls_last=True),
            "pk",
        )
        context["log_activity_url"] = _log_activity_url("contact", contact)
        context["audit_log"] = _audit_log_for(contact)
        return context


class ContactCreateView(SalesRoleRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Contact
    form_class = ContactForm
    template_name = "crm/contact_form.html"
    permission_required = "crm.add_contact"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["back"] = redirects.safe_next(self.request)
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        _record_audit_log(self.request.user, self.object, AuditLogEntry.Action.CREATED)
        messages.success(self.request, f"Created contact “{self.object}”.")
        return response

    def get_success_url(self):
        # Booked from the middle of a job? Go back with them chosen.
        target = redirects.safe_next(self.request)
        if target:
            return redirects.with_params(target, contact=self.object.pk)
        return super().get_success_url()


class ContactUpdateView(SalesRoleRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Contact
    form_class = ContactForm
    template_name = "crm/contact_form.html"
    permission_required = "crm.change_contact"

    def form_valid(self, form):
        previous = Contact.objects.get(pk=self.object.pk)
        # Tags are many-to-many: str() of the manager says nothing, and
        # after the save the old instance's manager already reads the
        # new tags — so record the names before saving.
        previous_tags = _tag_names(previous)
        response = super().form_valid(form)
        changed = [field for field in form.changed_data if field != "tags"]
        changes = _diff_changed_fields(previous, self.object, changed)
        if "tags" in form.changed_data:
            changes["tags"] = [previous_tags, _tag_names(self.object)]
        if changes:
            _record_audit_log(self.request.user, self.object, AuditLogEntry.Action.UPDATED, changes)
        messages.success(self.request, f"Updated contact “{self.object}”.")
        return response


def _tag_names(contact):
    return ", ".join(sorted(contact.tags.values_list("name", flat=True)))


class ContactDeactivateView(SalesRoleRequiredMixin, PermissionRequiredMixin, DetailView):
    """Same pattern as CompanyDeactivateView — is_active=False, never a
    hard delete. See that view's docstring for the reasoning."""

    model = Contact
    template_name = "crm/contact_confirm_deactivate.html"
    permission_required = "crm.change_contact"

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


class ActivityListView(SalesRoleRequiredMixin, PerPageMixin, ListView):
    model = Activity
    template_name = "crm/activity_list.html"
    context_object_name = "activities"
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset().select_related("company", "contact", "created_by")
        activity_type = self.request.GET.get("type")
        if activity_type in Activity.ActivityType.values:
            queryset = queryset.filter(activity_type=activity_type)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["activity_type"] = self.request.GET.get("type", "")
        context["type_choices"] = Activity.ActivityType.choices
        return context


class ActivityCreateView(SalesRoleRequiredMixin, PermissionRequiredMixin, CreateView):
    """No ActivityUpdateView exists, deliberately — Activity.save()
    itself rejects updates (docs/DATABASE_DESIGN.md, immutable history).
    No ActivityDetailView either: an Activity's "detail page" is the
    timeline on whichever Company or Contact it's attached to.
    """

    model = Activity
    form_class = ActivityForm
    template_name = "crm/activity_form.html"
    permission_required = "crm.add_activity"

    def get_initial(self):
        # Supports linking in from a specific record's detail page
        # (e.g. "Log a call" on a Company) via ?company=<id> etc., so
        # the relevant relation is pre-selected rather than making the
        # user pick it again.
        initial = super().get_initial()
        for field in ("company", "contact"):
            value = _int_or_none(self.request.GET.get(field))
            if value is not None:
                initial[field] = value
        return initial

    def get_context_data(self, **kwargs):
        # "Cancel" needs somewhere sensible to go back to even before a
        # save exists — reuses the same ?relation=<id> query params as
        # get_initial(), in the same priority order get_success_url()
        # uses after a save.
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = self._relation_url_from_query() or reverse("crm:activity_list")
        return context

    def _relation_url_from_query(self):
        models_by_field = {"company": Company, "contact": Contact}
        for field, model in models_by_field.items():
            value = _int_or_none(self.request.GET.get(field))
            if value is not None:
                related = model.objects.filter(pk=value).first()
                if related is not None:
                    return related.get_absolute_url()
        return None

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "Logged activity.")
        return response

    def get_success_url(self):
        activity = self.object
        for related in (activity.company, activity.contact):
            if related is not None:
                return related.get_absolute_url()
        return reverse("crm:activity_list")


class TaskListView(TasksHubMixin, SalesRoleRequiredMixin, PerPageMixin, ListView):
    hub_tab = "tasks"
    model = Task
    template_name = "crm/task_list.html"
    context_object_name = "tasks"
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset().select_related("assigned_to", "contact", "quote")

        kind = self.request.GET.get("kind")
        if kind in Task.Kind.values:
            queryset = queryset.filter(kind=kind)

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

        # A direct foreign key, so no join hazard here — unlike the
        # address filter on customers, which has to go through a
        # subquery to keep the paginator honest.
        contact_id = _int_or_none(self.request.GET.get("contact"))
        if contact_id is not None:
            queryset = queryset.filter(contact_id=contact_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status"] = self.request.GET.get("status", "")
        context["priority"] = self.request.GET.get("priority", "")
        context["mine"] = self.request.GET.get("mine") == "1"
        context["overdue"] = self.request.GET.get("overdue") == "1"
        context["status_choices"] = Task.Status.choices
        context["priority_choices"] = Task.Priority.choices
        context["kind"] = self.request.GET.get("kind", "")
        context["kind_choices"] = Task.Kind.choices
        # Narrowing to one customer also makes "Add task" open with them
        # already chosen — see crm/_hub_tabs.html.
        context["contact_id"] = _int_or_none(self.request.GET.get("contact"))
        context["contacts"] = contact_choices()
        return context


FOLLOW_UP_VIEWS = {
    # key: (label, status, ordering)
    "open": ("Open", Task.Status.PENDING, (F("due_date").asc(nulls_last=True), "pk")),
    "done": ("Done", Task.Status.COMPLETED, ("-completed_at", "-pk")),
    "dismissed": ("Dismissed", Task.Status.CANCELLED, ("-updated_at", "-pk")),
}


class FollowUpListView(TasksHubMixin, SalesRoleRequiredMixin, PerPageMixin, ListView):
    """Repeat-service follow-ups (apps/crm/followups.py): who's due,
    for what, with one-tap complete."""

    hub_tab = "followups"
    template_name = "crm/followup_list.html"
    context_object_name = "follow_ups"
    paginate_by = 25

    def get_queryset(self):
        params = self.request.GET
        _, status, ordering = FOLLOW_UP_VIEWS.get(params.get("show"), FOLLOW_UP_VIEWS["open"])
        queryset = Task.objects.filter(kind=Task.Kind.FOLLOW_UP, status=status).select_related(
            "contact", "service_type", "assigned_to"
        )
        if params.get("mine") == "1":
            queryset = queryset.filter(assigned_to=self.request.user)
        return queryset.order_by(*ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        show = self.request.GET.get("show")
        context["show"] = show if show in FOLLOW_UP_VIEWS else "open"
        context["show_choices"] = [(key, label) for key, (label, _, _) in FOLLOW_UP_VIEWS.items()]
        context["mine"] = self.request.GET.get("mine") == "1"
        context["today"] = timezone.localdate()
        return context


class PlanListView(TasksHubMixin, SalesRoleRequiredMixin, PerPageMixin, ListView):
    hub_tab = "plans"
    template_name = "crm/plan_list.html"
    context_object_name = "plans"
    paginate_by = 25

    def get_queryset(self):
        queryset = BusinessPlan.objects.select_related("owner").annotate(
            item_count=Count("items"), done_count=Count("items", filter=Q(items__is_done=True))
        )
        if self.request.GET.get("show") == "done":
            queryset = queryset.filter(status=BusinessPlan.Status.DONE)
        else:
            queryset = queryset.exclude(status=BusinessPlan.Status.DONE)
        return queryset.order_by(F("due_date").asc(nulls_last=True), "pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show"] = "done" if self.request.GET.get("show") == "done" else "active"
        return context


class PlanDetailView(TasksHubMixin, SalesRoleRequiredMixin, DetailView):
    hub_tab = "plans"
    model = BusinessPlan
    template_name = "crm/plan_detail.html"
    context_object_name = "plan"

    def get_queryset(self):
        return BusinessPlan.objects.select_related("owner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = list(self.object.items.all())
        context["items"] = items
        context["done_count"] = sum(item.is_done for item in items)
        context["item_form"] = ChecklistItemForm()
        return context


class PlanFormMixin(audit.AuditedFormMixin, SalesRoleRequiredMixin, PermissionRequiredMixin):
    """Write a plan. Owner and sales reps; `users/0004` gives cleaners
    no businessplan permissions, and the Tasks hub they live in is
    sales-and-owner anyway."""

    model = BusinessPlan
    form_class = BusinessPlanForm
    template_name = "crm/plan_form.html"
    hub_tab = "plans"

    def get_initial(self):
        initial = super().get_initial()
        # Most plans are the author's own, so offer that rather than an
        # empty picker — it is still a field, so it can be changed.
        initial.setdefault("owner", self.request.user.pk)
        return initial

    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Saved {self.object.title}.")
        return response


class PlanCreateView(PlanFormMixin, CreateView):
    permission_required = "crm.add_businessplan"


class PlanUpdateView(PlanFormMixin, UpdateView):
    permission_required = "crm.change_businessplan"


class ChecklistItemCreateView(SalesRoleRequiredMixin, PermissionRequiredMixin, View):
    """Add one step to a plan. POST only — it writes.

    Lands back on the plan with the box ready for the next step, since
    steps are usually added several in a row.
    """

    permission_required = "crm.add_planchecklistitem"

    def post(self, request, pk, *args, **kwargs):
        plan = get_object_or_404(BusinessPlan, pk=pk)
        form = ChecklistItemForm(request.POST)
        if not form.is_valid():
            for error in form.errors.get("text", ["That step couldn't be added."]):
                messages.warning(request, error)
            return redirect(plan.get_absolute_url())
        item = form.save(commit=False)
        item.plan = plan
        # Appended, not inserted: a checklist is a sequence of thoughts
        # and the order they arrived in is the useful one.
        item.position = (plan.items.aggregate(last=models.Max("position"))["last"] or 0) + 1
        item.save()
        audit.record(request.user, item, AuditLogEntry.Action.CREATED, {})
        return redirect(plan.get_absolute_url())


class ChecklistItemToggleView(SalesRoleRequiredMixin, PermissionRequiredMixin, View):
    """Tick a step off, or back on. POST only — it writes.

    One request per item, which is why it is this rather than a form
    over the whole checklist: ticking one step should not resubmit the
    other fourteen, and it keeps working with no JavaScript.

    Recorded in the change log, consistent with `JobStatusView` doing
    the same for a POST-only status change. The volume is real — a
    fifteen-step plan worked through over a week is fifteen entries —
    but the log is paginated and filterable by record type, and a log
    that records some writes and not others is worse than a noisy one.
    `undo.UNDOABLE_MODELS` does not list this model, so the entry is
    history rather than something with an Undo button.
    """

    permission_required = "crm.change_planchecklistitem"

    def post(self, request, pk, *args, **kwargs):
        item = get_object_or_404(PlanChecklistItem.objects.select_related("plan"), pk=pk)
        was = item.is_done
        item.is_done = not was
        item.save(update_fields=["is_done"])
        audit.record(
            request.user,
            item,
            AuditLogEntry.Action.UPDATED,
            {"is_done": [str(was), str(item.is_done)]},
        )
        return redirect(item.plan.get_absolute_url())


class ChecklistItemDeleteView(SalesRoleRequiredMixin, PermissionRequiredMixin, View):
    """Remove a step. POST only — it writes.

    A real delete, not a flag: a mistyped step is clutter, not history,
    and there is nothing to preserve. Without this, a typo would be
    permanent, which is the kind of hole that gets reported as a bug.

    Sales reps have `delete_planchecklistitem` in `users/0004`, unlike
    `delete_businessplan` — removing a step off your own list is not
    the same as discarding the plan.
    """

    permission_required = "crm.delete_planchecklistitem"

    def post(self, request, pk, *args, **kwargs):
        item = get_object_or_404(PlanChecklistItem.objects.select_related("plan"), pk=pk)
        plan, text = item.plan, item.text
        audit.record(request.user, item, AuditLogEntry.Action.UPDATED, {"removed": [text, ""]})
        item.delete()
        messages.success(request, f"Removed “{text}”.")
        return redirect(plan.get_absolute_url())


NOTE_FILTERS = {
    "": ("All", {}),
    "general": ("General", {"contact__isnull": True, "job__isnull": True}),
    "contact": ("About a customer", {"contact__isnull": False}),
    "job": ("About a job", {"job__isnull": False}),
}


class NoteListView(TasksHubMixin, SalesRoleRequiredMixin, PerPageMixin, ListView):
    """Notes, pinned first. Adding and editing notes lands in Phase 19."""

    hub_tab = "notes"
    template_name = "crm/note_list.html"
    context_object_name = "notes"
    paginate_by = 25

    def get_queryset(self):
        params = self.request.GET
        _, filters = NOTE_FILTERS.get(params.get("about", ""), NOTE_FILTERS[""])
        queryset = Note.objects.filter(**filters).select_related(
            "author", "contact", "job", "job__primary_service_type"
        )
        query = params.get("q", "").strip()
        if query:
            queryset = queryset.filter(body__icontains=query)
        return queryset.order_by("-pinned", "-created_at", "-pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        about = self.request.GET.get("about", "")
        context["about"] = about if about in NOTE_FILTERS else ""
        context["about_choices"] = [(key, label) for key, (label, _) in NOTE_FILTERS.items()]
        context["query"] = self.request.GET.get("q", "")
        return context


class TaskDetailView(SalesRoleRequiredMixin, DetailView):
    model = Task
    template_name = "crm/task_detail.html"
    context_object_name = "task"

    def get_queryset(self):
        # The page shows the customer's phone, email and company, and
        # the estimate it belongs to. Without this it fetches each of
        # them separately (CLAUDE.md's performance rules).
        return (
            super()
            .get_queryset()
            .select_related("contact", "contact__company", "quote", "assigned_to")
        )


def _notify_assignee(task, actor, previous_assignee_id=None):
    """Tell someone a task is now theirs.

    Never the person doing the assigning — nobody needs telling about
    their own action — and only when the assignment actually changed, so
    editing a task's title doesn't re-announce it.
    """
    assignee = task.assigned_to
    if assignee is None or assignee == actor or assignee.pk == previous_assignee_id:
        return
    kind = (
        Notification.Kind.FOLLOW_UP if task.kind == Task.Kind.FOLLOW_UP else Notification.Kind.TASK
    )
    notify(
        assignee,
        kind,
        f"{actor.get_full_name() or actor.get_username()} assigned you a task",
        task.title,
        task.get_absolute_url(),
    )


class TaskFormUserMixin:
    """Hand the form the person using it, so the estimate list can be
    scoped by what they're allowed to see.

    Also puts the chosen customer in the context, so the page can show
    their phone and email — a task about somebody is usually a task that
    means ringing them.
    """

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def chosen_contact(self):
        """The customer this task is about, if there is one yet.

        Three places to look, in order: what was just submitted, the
        saved record, then `?contact=`. The submitted value comes first
        because a form that fails validation is re-rendered — without
        it, picking a customer and then leaving the title blank would
        lose their details on the way back.

        Server-rendered either way, so changing the dropdown doesn't
        update it until the page is saved. That is the same trade-off
        the job form makes for its address list, and it is why the page
        works without JavaScript.
        """
        submitted = _int_or_none(self.request.POST.get("contact"))
        if submitted is not None:
            return Contact.objects.filter(pk=submitted).first()
        existing = getattr(self.object, "contact", None) if self.object else None
        if existing is not None:
            return existing
        asked_for = _int_or_none(self.request.GET.get("contact"))
        if asked_for is None:
            return None
        return Contact.objects.filter(pk=asked_for).first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["chosen_contact"] = self.chosen_contact()
        return context


class TaskCreateView(
    audit.AuditedFormMixin,
    TaskFormUserMixin,
    SalesRoleRequiredMixin,
    PermissionRequiredMixin,
    CreateView,
):
    model = Task
    form_class = TaskForm
    template_name = "crm/task_form.html"
    permission_required = "crm.add_task"

    def get_initial(self):
        initial = super().get_initial()
        initial.setdefault("assigned_to", self.request.user.pk)
        for field in ("contact", "quote", "job"):
            value = _int_or_none(self.request.GET.get(field))
            if value is not None:
                initial[field] = value
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        _apply_task_completion(form.instance, self.request.user, was_completed=False)
        response = super().form_valid(form)
        _notify_assignee(self.object, self.request.user)
        messages.success(self.request, f"Created task “{self.object.title}”.")
        return response


class TaskUpdateView(
    audit.AuditedFormMixin,
    TaskFormUserMixin,
    SalesRoleRequiredMixin,
    PermissionRequiredMixin,
    UpdateView,
):
    model = Task
    form_class = TaskForm
    template_name = "crm/task_form.html"
    permission_required = "crm.change_task"

    def form_valid(self, form):
        saved = Task.objects.filter(pk=form.instance.pk).values("status", "assigned_to").first()
        was_completed = bool(saved) and saved["status"] == Task.Status.COMPLETED
        previous_assignee = saved["assigned_to"] if saved else None
        _apply_task_completion(form.instance, self.request.user, was_completed)
        response = super().form_valid(form)
        _notify_assignee(self.object, self.request.user, previous_assignee)
        messages.success(self.request, f"Updated task “{self.object.title}”.")
        return response


class TaskCompleteView(SalesRoleRequiredMixin, PermissionRequiredMixin, View):
    """One-click completion from the list or detail page, without going
    through the full edit form — the dedicated "completion workflow"
    the roadmap calls for, separate from ordinary editing. POST only.

    Only acts on a pending task. The template only renders this action
    for pending tasks, but that's a UI-level guard only — without this
    check here too, a direct POST (e.g. a stale page, or the endpoint
    hit directly) could silently revive an already-cancelled task
    straight to completed.
    """

    permission_required = "crm.change_task"

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        if task.status != Task.Status.PENDING:
            messages.info(request, f"“{task.title}” is not pending and was left unchanged.")
            return redirect(task.get_absolute_url())

        task.status = Task.Status.COMPLETED
        _apply_task_completion(task, request.user, was_completed=False)
        task.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])
        # Not a form, so AuditedFormMixin can't see it.
        audit.record(
            request.user,
            task,
            AuditLogEntry.Action.UPDATED,
            {"status": [str(Task.Status.PENDING.label), str(Task.Status.COMPLETED.label)]},
        )
        messages.success(request, f"Completed “{task.title}”.")

        next_url = request.POST.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect(task.get_absolute_url())
