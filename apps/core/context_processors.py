from django.conf import settings
from django.urls import reverse

from apps.users.models import UserProfile
from apps.users.roles import user_role

from .navigation import build_navigation
from .notifications import bell

SIDEBAR_COOKIE = "crm_sidebar"


def logo_url(business):
    # The version query changes with every save, so a new logo shows at
    # once even though the logo response is cacheable.
    return f"{reverse('core:business_logo')}?v={int(business.updated_at.timestamp())}"


def app_shell(request):
    """Brand name everywhere; for logged-in users the role-filtered
    navigation, their saved theme, and whether they collapsed the
    sidebar (a cookie the page script sets, read here so the page
    renders collapsed from the first paint).

    Error pages (404/403) render through this too, where
    request.resolver_match may be None — hence the defensive getattr.
    """
    business = getattr(request, "business", None)
    context = {
        "brand_name": business.display_name if business else settings.CRM_BRAND_NAME,
        "brand_logo_url": logo_url(business) if business and business.logo else "",
        "support_email": settings.CRM_SUPPORT_EMAIL,
    }
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return context
    match = getattr(request, "resolver_match", None)
    has_role = bool(user_role(user))
    # No badges left since ADR 0014 retired the Inbox. Its unread count
    # was an aggregate over a per-channel subquery on **every** page
    # render for every logged-in user; `build_navigation` still takes
    # the mapping because the next badge will want it.
    context["nav"] = build_navigation(user, getattr(match, "view_name", "") or "", {})
    # The top bar's bell. Its list is rendered server-side (a <details>
    # dropdown works without JavaScript), which costs one indexed query
    # with a small LIMIT on every page — the price of the bell not
    # needing a round trip to open.
    if has_role:
        context["bell"] = bell(user)
    # Read, never create, the profile here — a GET shouldn't write.
    theme = UserProfile.objects.filter(user=user).values_list("theme", flat=True).first()
    context["theme"] = theme if theme in (UserProfile.Theme.LIGHT, UserProfile.Theme.DARK) else ""
    context["sidebar_collapsed"] = request.COOKIES.get(SIDEBAR_COOKIE) == "collapsed"
    return context
