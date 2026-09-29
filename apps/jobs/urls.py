from django.urls import path

from . import views

app_name = "jobs"

urlpatterns = [
    path("calendar/", views.CalendarView.as_view(), name="calendar"),
    path("jobs/<int:pk>/", views.JobDetailView.as_view(), name="job_detail"),
    path("tasks/quotes/", views.QuoteListView.as_view(), name="quote_list"),
    path("quotes/<int:pk>/", views.QuoteDetailView.as_view(), name="quote_detail"),
    path("financials/", views.FinancialsView.as_view(), name="financials"),
    path("settings/services/", views.ServiceListView.as_view(), name="service_list"),
    path(
        "settings/services/<int:pk>/edit/",
        views.ServiceUpdateView.as_view(),
        name="service_update",
    ),
]
