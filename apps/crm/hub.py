"""The Tasks hub's tabs (Phase 17 unit 3): general tasks, follow-ups,
quotes, business plans, and notes — separate pages sharing one tab bar,
so each keeps its own simple filters and pagination."""

from django.urls import reverse
from django.utils import timezone

from apps.jobs.models import Quote

from .models import Task

HUB_TABS = (
    ("tasks", "Tasks", "crm:task_list"),
    ("followups", "Follow-ups", "crm:task_followups"),
    ("quotes", "Quotes", "jobs:quote_list"),
    ("plans", "Plans", "crm:plan_list"),
    ("notes", "Notes", "crm:note_list"),
)


class TasksHubMixin:
    """Adds the tab bar. Subclasses set ``hub_tab`` to their key."""

    hub_tab = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        counts = {
            "followups": Task.objects.filter(
                kind=Task.Kind.FOLLOW_UP,
                status=Task.Status.PENDING,
                due_date__lte=timezone.localdate(),
            ).count(),
            "quotes": Quote.objects.filter(status__in=Quote.OPEN_STATUSES).count(),
        }
        context["hub_tabs"] = [
            {
                "label": label,
                "url": reverse(url_name),
                "current": key == self.hub_tab,
                "count": counts.get(key),
            }
            for key, label, url_name in HUB_TABS
        ]
        return context
