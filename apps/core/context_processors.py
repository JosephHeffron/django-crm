from django.conf import settings

from apps.messaging.services import unread_count
from apps.users.roles import user_role

from .navigation import build_navigation


def app_shell(request):
    """Brand name everywhere; role-filtered navigation for logged-in users.

    Error pages (404/403) render through this too, where
    request.resolver_match may be None — hence the defensive getattr.
    """
    context = {"brand_name": settings.CRM_BRAND_NAME}
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return context
    match = getattr(request, "resolver_match", None)
    badges = {"unread_messages": unread_count(user)} if user_role(user) else {}
    context["nav"] = build_navigation(user, getattr(match, "view_name", "") or "", badges)
    return context
