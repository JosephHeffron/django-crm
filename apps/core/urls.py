from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "search/",
        views.ComingSoonView.as_view(section_label="Search"),
        name="search",
    ),
]
