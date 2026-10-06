import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.navigation import all_links
from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.users.models import get_profile
from apps.users.roles import Role

User = get_user_model()
PASSWORD = "correct-horse-battery"


def _sidebar(html):
    return html.split('<nav id="sidebar"', 1)[1].split("</nav>", 1)[0]


def _sidebar_links(html):
    """(href, label, is_current) for every page link in the sidebar —
    direct links and flyout rows; not the logout button or footer."""
    body = _sidebar(html).split('<div class="sidebar-footer">', 1)[0]
    pattern = re.compile(
        r'<a class="(?:nav-link|flyout-link)" href="([^"]+)"( aria-current="page")?>\s*'
        r"<svg[^>]*>.*?</svg>\s*<span[^>]*>([^<]+)</span>",
        re.S,
    )
    return [(href, label, bool(current)) for href, current, label in pattern.findall(body)]


def _groups(html):
    return re.findall(
        r'<span class="nav-text">([^<]+)</span>\s*<svg class="icon nav-arrow"', _sidebar(html)
    )


class NavTestCase(TestCase):
    def login(self, role, username=None):
        username = username or f"user-{role or 'none'}"
        user = User.objects.create_user(username, password=PASSWORD)
        if role:
            grant_role(user, role)
        self.client.login(username=username, password=PASSWORD)
        return user

    def page(self, url="/"):
        return self.client.get(url).content.decode()


class SidebarStructureTests(NavTestCase):
    def test_sales_rep(self):
        self.login(Role.SALES_REP)
        html = self.page()
        self.assertEqual(_groups(html), ["Customers", "Crew", "Job"])
        self.assertEqual(
            [label for _, label, _ in _sidebar_links(html)],
            [
                "Dashboard",
                "Inbox",
                "Customers",
                "Companies",
                "Follow-ups",
                "Tasks",
                "Notes",
                "Activities",
                # A rep clocks their own time and plans the crew's week,
                # but doesn't see pay or the team list.
                "Time clock",
                "Assignments",
                "Scheduling",
                "Estimates",
                "Reports",
                "Map",
            ],
        )

    def test_owner_also_gets_crew_and_finance(self):
        self.login(Role.OWNER)
        self.assertEqual(_groups(self.page()), ["Customers", "Crew", "Job", "Finance"])

    def test_cleaner_and_no_role(self):
        self.login(Role.CLEANER)
        self.assertEqual(
            [label for _, label, _ in _sidebar_links(self.page())],
            ["Dashboard", "Inbox", "Time clock", "Scheduling"],
        )
        self.client.logout()
        self.login(None)
        self.assertEqual([label for _, label, _ in _sidebar_links(self.page())], ["Dashboard"])

    def test_most_specific_link_is_current_and_its_group_lights_up(self):
        self.login(Role.SALES_REP)
        html = self.page(reverse("crm:task_followups"))
        self.assertEqual(
            [label for _, label, current in _sidebar_links(html) if current], ["Follow-ups"]
        )
        self.assertIn('class="nav-group is-active"', html)

    def test_brand_and_workspace_label(self):
        self.login(Role.SALES_REP)
        html = self.page()
        self.assertIn('<span class="brand-name">Exterior CRM</span>', html)
        self.assertIn('<span class="brand-sub">Workspace</span>', html)
        self.assertIn("<title>Dashboard · Exterior CRM</title>", html)


# Every role's own pages, reached from the gear menu.
OWN_PAGES = ("people:profile", "people:profile_edit", "users:password_change")


class NavigationMatchesAccessForEveryRoleTests(NavTestCase):
    """The nav and the views are declared against the same role sets
    (ADR 0008). For each role: every link shown opens (200) and needs a
    login, and every navigation destination NOT shown is refused (403)
    — the two can never disagree."""

    def _check(self, role):
        self.login(role)
        shown = {href for href, _, _ in _sidebar_links(self.page())}
        for href in shown:
            self.assertEqual(self.client.get(href).status_code, 200, f"{role}: {href}")
        everywhere = {reverse(link.url_name) for link in all_links()}
        own = {reverse(name) for name in OWN_PAGES}
        for url in everywhere - shown - own:
            response = self.client.get(url)
            if role is None or url not in self._menu_urls():
                self.assertEqual(response.status_code, 403, f"{role}: {url}")
            else:
                self.assertEqual(response.status_code, 200, f"{role}: {url}")
        self.client.logout()
        for href in shown:
            self.assertEqual(self.client.get(href).status_code, 302, f"anonymous: {href}")
        return shown

    def _menu_urls(self):
        """Create/gear destinations this person was shown on the page."""
        html = self.page()
        return set(re.findall(r'<a class="dropdown-item" href="([^"]+)"', html))

    def test_owner(self):
        self.assertEqual(len(self._check(Role.OWNER)), 21)

    def test_sales_rep(self):
        self._check(Role.SALES_REP)

    def test_cleaner(self):
        self._check(Role.CLEANER)

    def test_no_role(self):
        self._check(None)


class TopBarTests(NavTestCase):
    def test_sales_roles_get_search_pill_and_create_menu(self):
        self.login(Role.SALES_REP)
        html = self.page()
        self.assertIn('placeholder="Search everything…"', html)
        create = html.split('aria-label="Create"', 1)[1].split("</details>", 1)[0]
        self.assertEqual(
            re.findall(r"</svg>([^<]+)</a>", create),
            ["New job", "New estimate", "New customer", "New task", "Log activity"],
        )

    def test_cleaner_gets_no_search_box_or_create_menu(self):
        self.login(Role.CLEANER)
        html = self.page()
        self.assertNotIn('role="search"', html)
        self.assertNotIn('aria-label="Create"', html)
        self.assertIn("data-palette-trigger", html)  # jump-to-page palette still

    def test_gear_menu_is_role_filtered(self):
        self.login(Role.SALES_REP)
        gear = self.page().split('aria-label="Settings"', 1)[1].split("</details>", 1)[0]
        self.assertIn("Your profile", gear)
        self.assertIn("Dark Mode", gear)
        self.assertNotIn("Company management", gear)
        self.client.logout()
        self.login(Role.OWNER, "boss")
        self.assertIn("Company management", self.page().split('aria-label="Settings"', 1)[1])

    def test_bottom_bar_per_role(self):
        def bar(html):
            section = html.split('<nav class="bottom-bar"', 1)[1].split("</nav>", 1)[0]
            return re.findall(r"<span>([^<]+)</span>", section)

        self.login(Role.SALES_REP)
        self.assertEqual(
            bar(self.page()), ["Dashboard", "Scheduling", "Customers", "Tasks", "Menu"]
        )
        self.client.logout()
        self.login(Role.CLEANER)
        self.assertEqual(bar(self.page()), ["Dashboard", "Scheduling", "Inbox", "Profile", "Menu"])

    def test_shortcuts_follow_roles(self):
        self.login(Role.CLEANER)
        html = self.page()
        self.assertIn('data-shortcut="g s"', html)
        self.assertNotIn('data-shortcut="g c"', html)

    def test_footer_email_links_only_when_configured(self):
        self.login(Role.SALES_REP)
        self.assertNotIn("Report a bug", self.page())
        with override_settings(CRM_SUPPORT_EMAIL="help@example.com"):
            html = self.page()
        self.assertIn('href="mailto:help@example.com?subject=Exterior%20CRM%20bug%20report"', html)
        self.assertIn("Ideas", html)

    def test_collapsed_sidebar_cookie(self):
        self.login(Role.SALES_REP)
        self.assertNotIn('class="sidebar-collapsed"', self.page())
        self.client.cookies["crm_sidebar"] = "collapsed"
        self.assertIn('<body class="sidebar-collapsed">', self.page())

    def test_logged_out_pages_use_the_auth_layout_without_nav(self):
        response = self.client.get(reverse("users:login"))
        self.assertContains(response, 'class="auth-layout"')
        self.assertNotContains(response, 'class="sidebar"')


class ThemeTests(NavTestCase):
    def test_saved_theme_is_rendered_on_html(self):
        user = self.login(Role.CLEANER)
        self.assertIn('<html lang="en">', self.page())
        response = self.client.post(
            reverse("people:theme"), {"theme": "dark", "next": "/calendar/"}
        )
        self.assertRedirects(response, "/calendar/")
        self.assertEqual(get_profile(user).theme, "dark")
        self.assertIn('<html lang="en" data-theme="dark">', self.page())

    def test_fetch_gets_204_and_system_clears_the_override(self):
        self.login(Role.CLEANER)
        response = self.client.post(
            reverse("people:theme"), {"theme": "system"}, headers={"X-Requested-With": "fetch"}
        )
        self.assertEqual(response.status_code, 204)
        self.assertIn('<html lang="en">', self.page())

    def test_bad_value_and_unsafe_next(self):
        self.login(Role.CLEANER)
        self.assertEqual(
            self.client.post(reverse("people:theme"), {"theme": "purple"}).status_code, 400
        )
        response = self.client.post(
            reverse("people:theme"), {"theme": "light", "next": "https://evil.example/"}
        )
        self.assertRedirects(response, "/")

    def test_requires_login(self):
        response = self.client.post(reverse("people:theme"), {"theme": "dark"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response["Location"])


class SearchSuggestTests(NavTestCase):
    def test_sales_roles_get_json_matches(self):
        user = self.login(Role.SALES_REP)
        contact = f.contact(user, "Pat", "Gutters", phone="(585) 555-0101")
        job = f.job(contact, user)
        url = reverse("core:search_suggest")
        rows = self.client.get(url, {"q": job.number}).json()["results"]
        self.assertEqual(
            rows[0],
            {
                "label": job.number,
                "detail": "Pat Gutters",
                "url": job.get_absolute_url(),
                "kind": "Job",
            },
        )
        rows = self.client.get(url, {"q": "Gutters"}).json()["results"]
        self.assertEqual(rows[0]["kind"], "Customer")
        self.assertEqual(self.client.get(url, {"q": "G"}).json(), {"results": []})

    def test_cleaners_are_refused(self):
        self.login(Role.CLEANER)
        self.assertEqual(
            self.client.get(reverse("core:search_suggest"), {"q": "Pat"}).status_code, 403
        )
