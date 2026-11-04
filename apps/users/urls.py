from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .login import LoginView

app_name = "users"

urlpatterns = [
    # Our subclass, not auth_views.LoginView: it counts failed
    # attempts (ADR 0020).
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "password-change/",
        auth_views.PasswordChangeView.as_view(
            success_url=reverse_lazy("users:password_change_done")
        ),
        name="password_change",
    ),
    path(
        "password-change/done/",
        auth_views.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
]
