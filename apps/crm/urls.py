from django.urls import path

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
    path("leads/", views.LeadListView.as_view(), name="lead_list"),
    path("leads/add/", views.LeadCreateView.as_view(), name="lead_create"),
    path("leads/<int:pk>/", views.LeadDetailView.as_view(), name="lead_detail"),
    path("leads/<int:pk>/edit/", views.LeadUpdateView.as_view(), name="lead_update"),
    path(
        "leads/<int:pk>/convert/",
        views.LeadConvertView.as_view(),
        name="lead_convert",
    ),
    path("deals/", views.DealListView.as_view(), name="deal_list"),
    path("deals/add/", views.DealCreateView.as_view(), name="deal_create"),
    path("deals/<int:pk>/", views.DealDetailView.as_view(), name="deal_detail"),
    path("deals/<int:pk>/edit/", views.DealUpdateView.as_view(), name="deal_update"),
    path("activities/", views.ActivityListView.as_view(), name="activity_list"),
    path("activities/add/", views.ActivityCreateView.as_view(), name="activity_create"),
    path("tasks/", views.TaskListView.as_view(), name="task_list"),
    path("tasks/add/", views.TaskCreateView.as_view(), name="task_create"),
    path("tasks/<int:pk>/", views.TaskDetailView.as_view(), name="task_detail"),
    path("tasks/<int:pk>/edit/", views.TaskUpdateView.as_view(), name="task_update"),
    path(
        "tasks/<int:pk>/complete/",
        views.TaskCompleteView.as_view(),
        name="task_complete",
    ),
]
