from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.views.generic import TemplateView

from apps.crm.models import Activity, Company, Contact, Deal, Lead, Task

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


class DashboardView(LoginRequiredMixin, TemplateView):
    """Operational at-a-glance summary — quick counts, open pipeline by
    stage, the signed-in user's own pending tasks, and recent activity
    across the CRM. Deliberately no charting library or JS dashboard
    framework (CLAUDE.md's "do not overengineer" rule) — every number
    here is a plain Django ORM aggregate, rendered server-side.
    """

    template_name = "core/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["company_count"] = Company.objects.filter(is_active=True).count()
        context["contact_count"] = Contact.objects.filter(is_active=True).count()
        # "Open" leads: not yet converted — a converted Lead's own
        # workflow is done (docs/DATABASE_DESIGN.md's Lifecycle
        # section), so it's no longer something to act on.
        context["open_lead_count"] = Lead.objects.exclude(status=Lead.Status.CONVERTED).count()
        context["pending_task_count"] = Task.objects.filter(status=Task.Status.PENDING).count()

        open_deals = Deal.objects.exclude(stage__in=Deal.CLOSED_STAGES)
        context["open_deal_count"] = open_deals.count()
        context["open_deal_value"] = open_deals.aggregate(total=Sum("value"))["total"] or 0

        stage_counts = {
            row["stage"]: row
            for row in Deal.objects.values("stage").annotate(
                count=Count("id"), total_value=Sum("value")
            )
        }
        # Iterate Deal.Stage.choices (not the raw annotated queryset)
        # so the breakdown follows the pipeline's natural order —
        # Meta.ordering doesn't apply to .values().annotate(), and an
        # alphabetical fallback would scramble prospecting → ... →
        # closed_lost into a meaningless sequence.
        context["deals_by_stage"] = [
            {
                "label": label,
                "count": stage_counts.get(value, {}).get("count", 0),
                "total_value": stage_counts.get(value, {}).get("total_value") or 0,
            }
            for value, label in Deal.Stage.choices
        ]

        context["my_tasks"] = (
            Task.objects.filter(assigned_to=self.request.user, status=Task.Status.PENDING)
            .select_related("contact", "deal")
            .order_by("due_date", "pk")[:DASHBOARD_LIST_LIMIT]
        )

        context["recent_activities"] = Activity.objects.select_related(
            "created_by", "company", "contact", "lead", "deal"
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
