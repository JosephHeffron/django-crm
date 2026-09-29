import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.navigation import NAV_ITEMS
from apps.crm.tests._helpers import grant_role
from apps.users.roles import Role

User = get_user_model()
PASSWORD = "correct-horse-battery"


def _sidebar_links(html):
    """(href, label, is_current) for every main sidebar nav link — the
    account links in the sidebar footer are deliberately excluded."""
    html = html.split('<nav id="sidebar"', 1)[1].split('<div class="sidebar-footer">', 1)[0]
    pattern = re.compile(
        r'<a class="nav-link" href="([^"]+)"( aria-current="page")?>\s*'
        r"<svg[^>]*>.*?</svg>\s*<span>([^<]+)</span>",
        re.S,
    )
    return [(href, label, bool(current)) for href, current, label in pattern.findall(html)]


class NavigationForSalesRepTests(TestCase):
    """Every nav link should point at a real, working page — the nav is
    only worth as much as its links actually resolve."""

    def setUp(self):
        grant_role(User.objects.create_user("alice", password=PASSWORD))
        self.client.login(username="alice", password=PASSWORD)

    def test_nav_lists_every_crm_section(self):
        labels = [label for _, label, _ in _sidebar_links(self.client.get("/").content.decode())]
        self.assertEqual(
            labels, ["Dashboard", "Contacts", "Tasks", "Companies", "Leads", "Deals", "Activities"]
        )

    def test_each_nav_url_is_reachable_and_login_required(self):
        for href, label, _ in _sidebar_links(self.client.get("/").content.decode()):
            self.client.logout()
            self.assertEqual(
                self.client.get(href).status_code, 302, f"{label} should require login"
            )
            self.client.login(username="alice", password=PASSWORD)
            response = self.client.get(href)
            self.assertEqual(response.status_code, 200, f"{label} should render")
            self.assertContains(response, label)

    def test_current_nav_section_is_marked_for_orientation(self):
        links = _sidebar_links(self.client.get(reverse("crm:company_list")).content.decode())
        current = [label for _, label, is_current in links if is_current]
        self.assertEqual(current, ["Companies"])

    def test_detail_pages_mark_their_section_current(self):
        response = self.client.get(reverse("crm:company_create"))
        current = [
            label
            for _, label, is_current in _sidebar_links(response.content.decode())
            if is_current
        ]
        self.assertEqual(current, ["Companies"])

    def test_dashboard_is_marked_current_on_the_dashboard(self):
        links = _sidebar_links(self.client.get(reverse("core:index")).content.decode())
        self.assertEqual([label for _, label, is_current in links if is_current], ["Dashboard"])

    def test_search_box_shown(self):
        self.assertContains(self.client.get("/"), 'role="search"')


class NavigationMatchesAccessForEveryRoleTests(TestCase):
    """The nav and the views are declared against the same role sets
    (ADR 0008). For each role: every link shown opens (200), and every
    nav page NOT shown is refused (403) — the two can never disagree."""

    def _check(self, role):
        username = f"user-{role or 'none'}"
        user = User.objects.create_user(username, password=PASSWORD)
        if role:
            grant_role(user, role)
        self.client.login(username=username, password=PASSWORD)

        shown = {href for href, _, _ in _sidebar_links(self.client.get("/").content.decode())}
        for item in NAV_ITEMS:
            url = reverse(item.url_name)
            expected = 200 if url in shown else 403
            self.assertEqual(self.client.get(url).status_code, expected, f"{role}: {url}")
        return shown

    def test_owner(self):
        self.assertEqual(len(self._check(Role.OWNER)), len(NAV_ITEMS))

    def test_sales_rep(self):
        self.assertEqual(len(self._check(Role.SALES_REP)), len(NAV_ITEMS))

    def test_cleaner(self):
        self.assertEqual(self._check(Role.CLEANER), {reverse("core:index")})

    def test_no_role(self):
        self.assertEqual(self._check(None), {reverse("core:index")})


class ShellTests(TestCase):
    def test_cleaner_gets_no_search_box(self):
        grant_role(User.objects.create_user("crew", password=PASSWORD), Role.CLEANER)
        self.client.login(username="crew", password=PASSWORD)
        self.assertNotContains(self.client.get("/"), 'role="search"')

    def test_shell_shows_name_initials_and_role(self):
        user = User.objects.create_user(
            "jdoe", password=PASSWORD, first_name="Jane", last_name="Doe"
        )
        grant_role(user, Role.SALES_REP)
        self.client.login(username="jdoe", password=PASSWORD)
        response = self.client.get("/")
        self.assertContains(response, "Jane Doe")
        self.assertContains(response, ">JD</span>")
        self.assertContains(response, "Sales Rep")

    def test_phone_bottom_bar_has_primary_items_and_menu(self):
        grant_role(User.objects.create_user("alice", password=PASSWORD))
        self.client.login(username="alice", password=PASSWORD)
        html = self.client.get("/").content.decode()
        bar = html.split('<nav class="bottom-bar"', 1)[1].split("</nav>", 1)[0]
        self.assertEqual(
            re.findall(r"<span>([^<]+)</span>", bar), ["Dashboard", "Contacts", "Tasks", "Menu"]
        )

    def test_brand_name_in_title(self):
        grant_role(User.objects.create_user("alice", password=PASSWORD))
        self.client.login(username="alice", password=PASSWORD)
        self.assertContains(self.client.get("/"), "<title>Dashboard · Exterior CRM</title>")

    def test_logged_out_pages_use_the_auth_layout_without_nav(self):
        response = self.client.get(reverse("users:login"))
        self.assertContains(response, 'class="auth-layout"')
        self.assertNotContains(response, 'class="sidebar"')
