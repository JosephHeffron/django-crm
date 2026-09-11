from django.urls import path

from apps.core.views import ComingSoonView

app_name = "crm"

urlpatterns = [
    path(
        "companies/",
        ComingSoonView.as_view(section_label="Companies"),
        name="company_list",
    ),
    path(
        "contacts/",
        ComingSoonView.as_view(section_label="Contacts"),
        name="contact_list",
    ),
    path(
        "leads/",
        ComingSoonView.as_view(section_label="Leads"),
        name="lead_list",
    ),
    path(
        "deals/",
        ComingSoonView.as_view(section_label="Deals"),
        name="deal_list",
    ),
    path(
        "activities/",
        ComingSoonView.as_view(section_label="Activities"),
        name="activity_list",
    ),
    path(
        "tasks/",
        ComingSoonView.as_view(section_label="Tasks"),
        name="task_list",
    ),
]
