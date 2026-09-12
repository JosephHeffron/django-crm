from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import render
from django.views.generic import TemplateView

from apps.crm.models import Company, Contact, Deal, Lead, Task

# Caps each category's results rather than paginating each one
# separately — simpler, and a search this wide (five models at once)
# should point the user to a more specific query long before this
# limit matters (CLAUDE.md's Performance Rules: paginate user-facing
# lists, don't load unbounded record sets).
SEARCH_RESULTS_PER_MODEL = 20


@login_required
def index(request):
    return render(request, "core/index.html")


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


class SearchView(LoginRequiredMixin, TemplateView):
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
