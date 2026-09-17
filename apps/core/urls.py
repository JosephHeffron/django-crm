from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="index"),
    path("search/", views.SearchView.as_view(), name="search"),
    path("health/", views.HealthCheckView.as_view(), name="health"),
]
