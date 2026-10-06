from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="index"),
    path("search/", views.SearchView.as_view(), name="search"),
    path("search/suggest/", views.SearchSuggestView.as_view(), name="search_suggest"),
    path("health/", views.HealthCheckView.as_view(), name="health"),
    path("manifest.webmanifest", views.ManifestView.as_view(), name="manifest"),
    path("sw.js", views.ServiceWorkerView.as_view(), name="service_worker"),
    path("offline/", views.OfflineView.as_view(), name="offline"),
    path("styleguide/", views.StyleguideView.as_view(), name="styleguide"),
    path("settings/business/", views.BusinessSettingsView.as_view(), name="business_settings"),
    path("settings/business/export/", views.BusinessExportView.as_view(), name="business_export"),
    path("branding/logo/", views.BusinessLogoView.as_view(), name="business_logo"),
    path("settings/", views.SettingsHubView.as_view(), name="settings"),
    path("settings/goals/", views.GoalsView.as_view(), name="goals"),
    path("settings/customize/", views.CustomizeView.as_view(), name="customize"),
    path("settings/activity/", views.ActivityLogView.as_view(), name="activity_log"),
    path(
        "settings/activity/<int:pk>/undo/",
        views.ActivityUndoView.as_view(),
        name="activity_undo",
    ),
    path("whats-new/", views.WhatsNewView.as_view(), name="whats_new"),
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    path(
        "notifications/<int:pk>/read/",
        views.NotificationReadView.as_view(),
        name="notification_read",
    ),
    path(
        "notifications/read-all/",
        views.NotificationReadAllView.as_view(),
        name="notifications_read_all",
    ),
    path(
        "onboarding/dismiss/",
        views.OnboardingDismissView.as_view(),
        name="onboarding_dismiss",
    ),
]
