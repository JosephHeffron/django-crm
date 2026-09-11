from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import CompanyForm
from .models import Company


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


class CompanyDeleteView(LoginRequiredMixin, DeleteView):
    model = Company
    template_name = "crm/company_confirm_delete.html"
    success_url = reverse_lazy("crm:company_list")

    def form_valid(self, form):
        name = self.object.name
        try:
            response = super().form_valid(form)
        except ProtectedError:
            # Deal.company uses on_delete=PROTECT (docs/DATABASE_DESIGN.md
            # finding #6) — a company with any deal history can't be hard-
            # deleted. Show that as a normal validation-style message
            # instead of an unhandled 500.
            messages.error(
                self.request,
                f"Can't delete “{name}” — it still has deals on record. "
                "Mark it inactive instead, or remove its deals first.",
            )
            return redirect(self.object.get_absolute_url())
        messages.success(self.request, f"Deleted company “{name}”.")
        return response
