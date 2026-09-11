from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import ActivityForm, CompanyForm, ContactForm, DealForm, LeadConversionForm, LeadForm
from .models import Activity, Company, Contact, Deal, Lead


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
        return context


class CompanyCreateView(LoginRequiredMixin, CreateView):
    model = Company
    form_class = CompanyForm
    template_name = "crm/company_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Created company “{self.object.name}”.")
        return response


class CompanyUpdateView(LoginRequiredMixin, UpdateView):
    model = Company
    form_class = CompanyForm
    template_name = "crm/company_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
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
        company.is_active = False
        company.save(update_fields=["is_active"])
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
        return context


class ContactCreateView(LoginRequiredMixin, CreateView):
    model = Contact
    form_class = ContactForm
    template_name = "crm/contact_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Created contact “{self.object}”.")
        return response


class ContactUpdateView(LoginRequiredMixin, UpdateView):
    model = Contact
    form_class = ContactForm
    template_name = "crm/contact_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Updated contact “{self.object}”.")
        return response


class ContactDeactivateView(LoginRequiredMixin, DetailView):
    """Same pattern as CompanyDeactivateView — is_active=False, never a
    hard delete. See that view's docstring for the reasoning."""

    model = Contact
    template_name = "crm/contact_confirm_deactivate.html"

    def post(self, request, *args, **kwargs):
        contact = self.get_object()
        contact.is_active = False
        contact.save(update_fields=["is_active"])
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
        return context


class LeadCreateView(LoginRequiredMixin, CreateView):
    model = Lead
    form_class = LeadForm
    template_name = "crm/lead_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Created lead “{self.object.name}”.")
        return response


class LeadUpdateView(LoginRequiredMixin, UpdateView):
    model = Lead
    form_class = LeadForm
    template_name = "crm/lead_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
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

        deal = None
        if data["create_deal"]:
            deal = Deal.objects.create(
                title=data["deal_title"],
                company=company,
                contact=contact,
                value=data["deal_value"],
                created_by=request.user,
            )

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
        return context


class DealCreateView(LoginRequiredMixin, CreateView):
    model = Deal
    form_class = DealForm
    template_name = "crm/deal_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        _sync_deal_closed_at(form.instance)
        response = super().form_valid(form)
        messages.success(self.request, f"Created deal “{self.object.title}”.")
        return response


class DealUpdateView(LoginRequiredMixin, UpdateView):
    model = Deal
    form_class = DealForm
    template_name = "crm/deal_form.html"

    def form_valid(self, form):
        _sync_deal_closed_at(form.instance)
        response = super().form_valid(form)
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
