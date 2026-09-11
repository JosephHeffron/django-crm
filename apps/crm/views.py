from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import redirect
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import CompanyForm, ContactForm
from .models import Company, Contact


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
