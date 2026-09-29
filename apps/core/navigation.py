"""The app's navigation, declared once against the same role sets the
views enforce (apps/users/roles.py, ADR 0008) — so a nav link is only
ever shown to users its page will actually let in.
"""

from dataclasses import dataclass

from django.urls import reverse

from apps.users.roles import ALL_ROLES, OWNER_ONLY, SALES_ROLES, user_role

# Phone bottom bar: this many primary items, plus a "Menu" button that
# opens the full drawer (which also holds the account links).
BOTTOM_BAR_SLOTS = 4


@dataclass(frozen=True)
class NavItem:
    label: str
    url_name: str
    icon: str
    roles: frozenset
    # View-name prefixes that mark this item as the current section.
    active_prefixes: tuple
    primary: bool = False


NAV_ITEMS = (
    NavItem("Dashboard", "core:index", "home", ALL_ROLES, ("core:index",), primary=True),
    NavItem(
        "Calendar",
        "jobs:calendar",
        "calendar",
        ALL_ROLES,
        ("jobs:calendar", "jobs:job_"),
        primary=True,
    ),
    NavItem("Contacts", "crm:contact_list", "users", SALES_ROLES, ("crm:contact_",), primary=True),
    NavItem(
        "Tasks",
        "crm:task_list",
        "check",
        SALES_ROLES,
        ("crm:task_", "crm:plan_", "crm:note_", "jobs:quote_"),
        primary=True,
    ),
    NavItem("Financials", "jobs:financials", "dollar", OWNER_ONLY, ("jobs:financials",)),
    NavItem("Companies", "crm:company_list", "building", SALES_ROLES, ("crm:company_",)),
    NavItem("Activities", "crm:activity_list", "activity", SALES_ROLES, ("crm:activity_",)),
    # Leads and Deals were folded into Contacts and Quotes (ADR 0009);
    # their old pages stay reachable by URL until Phase 18 removes them.
    NavItem("Services", "jobs:service_list", "settings", OWNER_ONLY, ("jobs:service_",)),
)


def _visible(item, role):
    # The dashboard is every logged-in user's landing page, including
    # a user with no role yet (who sees a "no role assigned" notice).
    return item.url_name == "core:index" or role in item.roles


def build_navigation(user, view_name):
    role = user_role(user)
    items = [
        {
            "label": item.label,
            "url": reverse(item.url_name),
            "icon": item.icon,
            "active": any(view_name.startswith(p) for p in item.active_prefixes),
            "primary": item.primary,
        }
        for item in NAV_ITEMS
        if _visible(item, role)
    ]
    full_name = user.get_full_name().strip()
    if user.first_name and user.last_name:
        initials = user.first_name[0] + user.last_name[0]
    else:
        initials = (full_name or user.get_username())[:2]
    return {
        "role": role,
        "role_label": role.value if role else "No role",
        "display_name": full_name or user.get_username(),
        "initials": initials.upper(),
        "items": items,
        "bottom_items": [i for i in items if i["primary"]][:BOTTOM_BAR_SLOTS],
        "show_search": role in SALES_ROLES,
    }
