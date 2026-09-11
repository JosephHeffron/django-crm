from django.urls import path

from apps.core.views import ComingSoonView

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
