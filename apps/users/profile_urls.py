"""Profile and team pages, at the site root (the auth views in urls.py
live under /accounts/)."""

from django.urls import path

from . import views

app_name = "people"

urlpatterns = [
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/edit/", views.ProfileEditView.as_view(), name="profile_edit"),
    path("team/", views.TeamListView.as_view(), name="team"),
    path("team/<str:username>/", views.TeamMemberView.as_view(), name="member"),
]
