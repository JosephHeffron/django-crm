from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views.generic import TemplateView


@login_required
def index(request):
    return render(request, "core/index.html")


class ComingSoonView(LoginRequiredMixin, TemplateView):
    """Placeholder for a nav section whose real views don't exist yet.

    Used with .as_view(section_label="...") from each app's urls.py so
    the navigation always has a working link, even before that
    section's CRUD is built.
    """

    template_name = "core/coming_soon.html"
    section_label = "This section"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section_label"] = self.section_label
        return context
