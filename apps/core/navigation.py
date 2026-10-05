"""The app's navigation (Phase 17.5 shell, ADR 0010), declared once
against the same role sets the views enforce (apps/users/roles.py,
ADR 0008) — so a link is only ever shown to people its page lets in.

The sidebar has direct links (Dashboard, Inbox) and groups that open a
flyout (Customers, Crew, Job, Finance). A group with no link visible
to the person is hidden. The Create and settings-gear menus and the
phone bottom bar are declared here too, so the command palette and the
role tests can see every destination in one place.
"""

from dataclasses import dataclass, field

from django.urls import reverse

from apps.users.roles import ALL_ROLES, OWNER_ONLY, SALES_ROLES, Role, user_role

# Phone bottom bar: this many items, plus a "Menu" button that opens the
# full drawer.
BOTTOM_BAR_SLOTS = 4


@dataclass(frozen=True)
class NavLink:
    label: str
    url_name: str
    icon: str  # line icon (#icon-*) for flyout rows, menus, bottom bar
    roles: frozenset
    # View-name prefixes that mark this link current. When several links
    # match, the longest prefix wins (Follow-ups beats Tasks).
    active_prefixes: tuple = ()
    badge: str = ""  # key into the badges build_navigation() is given
    shortcut: str = ""  # two-key sequence, e.g. "g c" (static/js/nav.js)


@dataclass(frozen=True)
class NavSection:
    label: str
    icon: str  # multi-color icon (#nav-*) for the sidebar row
    link: NavLink | None = None  # a direct link …
    children: tuple = field(default_factory=tuple)  # … or a flyout group


SECTIONS = (
    NavSection(
        "Dashboard",
        "dashboard",
        link=NavLink("Dashboard", "core:index", "home", ALL_ROLES, ("core:index",), shortcut="g d"),
    ),
    NavSection(
        "Inbox",
        "inbox",
        # Team messages until customer texting exists (Phase 24).
        link=NavLink(
            "Inbox",
            "messaging:home",
            "inbox",
            ALL_ROLES,
            ("messaging:",),
            badge="unread_messages",
            shortcut="g i",
        ),
    ),
    NavSection(
        "Customers",
        "customers",
        children=(
            NavLink(
                "Customers",
                "crm:contact_list",
                "users",
                SALES_ROLES,
                ("crm:contact_",),
                shortcut="g c",
            ),
            NavLink("Companies", "crm:company_list", "building", SALES_ROLES, ("crm:company_",)),
            NavLink(
                "Follow-ups",
                "crm:task_followups",
                "refresh",
                SALES_ROLES,
                ("crm:task_followups",),
                shortcut="g f",
            ),
            NavLink(
                "Tasks",
                "crm:task_list",
                "check",
                SALES_ROLES,
                ("crm:task_", "crm:plan_"),
                shortcut="g t",
            ),
            NavLink("Notes", "crm:note_list", "message", SALES_ROLES, ("crm:note_",)),
            NavLink("Activities", "crm:activity_list", "activity", SALES_ROLES, ("crm:activity_",)),
        ),
    ),
    NavSection(
        "Crew",
        "crew",
        children=(
            NavLink("Team", "people:team", "users", OWNER_ONLY, ("people:team", "people:member")),
        ),
    ),
    NavSection(
        "Job",
        "job",
        children=(
            NavLink(
                "Scheduling",
                "jobs:calendar",
                "calendar",
                ALL_ROLES,
                ("jobs:calendar", "jobs:job_"),
                shortcut="g s",
            ),
            NavLink(
                "Estimates",
                "jobs:quote_list",
                "briefcase",
                SALES_ROLES,
                ("jobs:quote_",),
                shortcut="g e",
            ),
        ),
    ),
    NavSection(
        "Finance",
        "finance",
        children=(
            NavLink("Financials", "jobs:financials", "dollar", OWNER_ONLY, ("jobs:financials",)),
        ),
    ),
)

# Phone bottom bar per role: a cleaner's own day, a seller's pipeline.
BOTTOM_BAR = {
    Role.OWNER: ("core:index", "jobs:calendar", "crm:contact_list", "crm:task_list"),
    Role.SALES_REP: ("core:index", "jobs:calendar", "crm:contact_list", "crm:task_list"),
    Role.CLEANER: ("core:index", "jobs:calendar", "messaging:home", "people:profile"),
}

CREATE_MENU = (
    NavLink("New customer", "crm:contact_create", "user-plus", SALES_ROLES, shortcut="n c"),
    NavLink("New task", "crm:task_create", "check", SALES_ROLES, shortcut="n t"),
    NavLink("Log activity", "crm:activity_create", "activity", SALES_ROLES),
)

# The dashboard's shortcut grid (Phase 17.5 step 4). Every tile is a
# page that exists; a role only sees the ones it may open.
QUICK_ACTIONS = (
    NavLink("New customer", "crm:contact_create", "user-plus", SALES_ROLES),
    NavLink("New task", "crm:task_create", "check", SALES_ROLES),
    NavLink("Log activity", "crm:activity_create", "activity", SALES_ROLES),
    NavLink("Schedule", "jobs:calendar", "calendar", ALL_ROLES),
    NavLink("Estimates", "jobs:quote_list", "briefcase", SALES_ROLES),
    NavLink("Follow-ups", "crm:task_followups", "refresh", SALES_ROLES),
    NavLink("Financials", "jobs:financials", "dollar", OWNER_ONLY),
    NavLink("Inbox", "messaging:home", "inbox", ALL_ROLES),
)

GEAR_MENU = (
    NavLink("Business settings", "core:business_settings", "building", OWNER_ONLY),
    NavLink("Monthly goals", "core:goals", "target", OWNER_ONLY),
    NavLink("Your profile", "people:profile", "user", ALL_ROLES),
    NavLink("Account settings", "people:profile_edit", "settings", ALL_ROLES),
    NavLink("Company management", "people:team", "users", OWNER_ONLY),
    NavLink("Customize", "jobs:service_list", "sparkles", OWNER_ONLY),
    NavLink("Change password", "users:password_change", "key", ALL_ROLES),
)

# Destinations outside the sidebar that the bottom bar can point at.
EXTRA_LINKS = (NavLink("Profile", "people:profile", "user", ALL_ROLES, ("people:",)),)


def _allowed(link, role):
    # The dashboard is every logged-in user's landing page, including a
    # user with no role yet (who sees a "no role assigned" notice).
    return link.url_name == "core:index" or role in link.roles


def _match_length(link, view_name):
    return max((len(p) for p in link.active_prefixes if view_name.startswith(p)), default=0)


def sidebar_links():
    return [
        link
        for section in SECTIONS
        for link in ([section.link] if section.link else section.children)
    ]


def all_links():
    """Every NavLink anywhere in the navigation (sidebar and menus)."""
    return sidebar_links() + list(CREATE_MENU) + list(GEAR_MENU)


def quick_actions(user):
    """The dashboard's shortcut tiles for this person."""
    role = user_role(user)
    return [
        {"label": link.label, "url": reverse(link.url_name), "icon": link.icon}
        for link in QUICK_ACTIONS
        if _allowed(link, role)
    ]


def build_navigation(user, view_name, badges=None):
    role = user_role(user)
    badges = badges or {}
    links = sidebar_links()
    best = max((_match_length(link, view_name) for link in links), default=0)

    def item(link, active=None):
        if active is None:
            active = best > 0 and _match_length(link, view_name) == best
        return {
            "label": link.label,
            "url": reverse(link.url_name),
            "icon": link.icon,
            "active": active,
            "badge": badges.get(link.badge) if link.badge else None,
            "shortcut": link.shortcut,
        }

    sections = []
    for section in SECTIONS:
        if section.link:
            if _allowed(section.link, role):
                sections.append(
                    {
                        **item(section.link),
                        "label": section.label,
                        "icon": section.icon,
                        "line_icon": section.link.icon,
                    }
                )
            continue
        children = [item(link) for link in section.children if _allowed(link, role)]
        if children:
            sections.append(
                {
                    "label": section.label,
                    "icon": section.icon,
                    "key": section.label.lower(),
                    "children": children,
                    "active": any(child["active"] for child in children),
                }
            )

    by_name = {link.url_name: link for link in links + list(EXTRA_LINKS)}
    bottom = [
        item(by_name[name], active=_match_length(by_name[name], view_name) > 0)
        for name in BOTTOM_BAR.get(role, ("core:index",))
    ][:BOTTOM_BAR_SLOTS]

    full_name = user.get_full_name().strip()
    if user.first_name and user.last_name:
        initials = user.first_name[0] + user.last_name[0]
    else:
        initials = (full_name or user.get_username())[:2]
    return {
        "role": role,
        "role_label": role.value if role else "No role",
        "display_name": full_name or user.get_username(),
        # For the dashboard's greeting, which wants a first name.
        "first_name": user.first_name or full_name or user.get_username(),
        "initials": initials.upper(),
        "sections": sections,
        "bottom_items": bottom,
        "create_items": [item(link, active=False) for link in CREATE_MENU if _allowed(link, role)],
        "gear_items": [item(link, active=False) for link in GEAR_MENU if _allowed(link, role)],
        "show_search": role in SALES_ROLES,
        "shortcuts": [
            {"keys": link.shortcut, "label": link.label}
            for link in all_links()
            if link.shortcut and _allowed(link, role)
        ],
    }
