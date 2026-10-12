from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "crm"

urlpatterns = [
    path("companies/", views.CompanyListView.as_view(), name="company_list"),
    path("companies/add/", views.CompanyCreateView.as_view(), name="company_create"),
    path("companies/<int:pk>/", views.CompanyDetailView.as_view(), name="company_detail"),
    path(
        "companies/<int:pk>/edit/",
        views.CompanyUpdateView.as_view(),
        name="company_update",
    ),
    path(
        "companies/<int:pk>/deactivate/",
        views.CompanyDeactivateView.as_view(),
        name="company_deactivate",
    ),
    path("contacts/", views.ContactListView.as_view(), name="contact_list"),
    path("contacts/add/", views.ContactCreateView.as_view(), name="contact_create"),
    path("contacts/<int:pk>/", views.ContactDetailView.as_view(), name="contact_detail"),
    path(
        "contacts/<int:pk>/edit/",
        views.ContactUpdateView.as_view(),
        name="contact_update",
    ),
    path(
        "contacts/<int:pk>/deactivate/",
        views.ContactDeactivateView.as_view(),
        name="contact_deactivate",
    ),
    # Leads and deals were folded into customers and estimates in
    # Phase 17 and retired in Phase 18 unit 5. The two list URLs
    # redirect rather than 404, because they were linked from the menu
    # for most of this project's life and somebody will have bookmarked
    # them. The detail URLs are gone: there is no row to point at.
    path(
        "leads/",
        RedirectView.as_view(pattern_name="crm:contact_list", permanent=True, query_string=True),
        name="lead_list",
    ),
    path(
        "deals/",
        RedirectView.as_view(pattern_name="jobs:quote_list", permanent=True),
        name="deal_list",
    ),
    path("activities/", views.ActivityListView.as_view(), name="activity_list"),
    path("activities/add/", views.ActivityCreateView.as_view(), name="activity_create"),
    path("tasks/", views.TaskListView.as_view(), name="task_list"),
    path("tasks/follow-ups/", views.FollowUpListView.as_view(), name="task_followups"),
    path("tasks/plans/", views.PlanListView.as_view(), name="plan_list"),
    path("tasks/plans/<int:pk>/", views.PlanDetailView.as_view(), name="plan_detail"),
    path("tasks/notes/", views.NoteListView.as_view(), name="note_list"),
    path("tasks/notes/new/", views.NoteCreateView.as_view(), name="note_create"),
    path("tasks/notes/<int:pk>/edit/", views.NoteUpdateView.as_view(), name="note_update"),
    path("addresses/add/", views.PropertyCreateView.as_view(), name="property_create"),
    path("addresses/<int:pk>/edit/", views.PropertyUpdateView.as_view(), name="property_update"),
    path("tasks/add/", views.TaskCreateView.as_view(), name="task_create"),
    path("tasks/<int:pk>/", views.TaskDetailView.as_view(), name="task_detail"),
    path("tasks/<int:pk>/edit/", views.TaskUpdateView.as_view(), name="task_update"),
    path(
        "tasks/<int:pk>/complete/",
        views.TaskCompleteView.as_view(),
        name="task_complete",
    ),
]
