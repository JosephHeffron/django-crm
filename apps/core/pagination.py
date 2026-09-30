"""Page-size choice for list pages: ?per_page=10|25|50|100, used by
templates/partials/_pagination.html. Anything else falls back to the
view's paginate_by."""

PER_PAGE_CHOICES = (10, 25, 50, 100)


class PerPageMixin:
    paginate_by = 25

    def get_paginate_by(self, queryset):
        value = self.request.GET.get("per_page", "")
        if value.isdigit() and int(value) in PER_PAGE_CHOICES:
            return int(value)
        return self.paginate_by

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["per_page_choices"] = PER_PAGE_CHOICES
        context["per_page"] = self.get_paginate_by(None)
        return context
