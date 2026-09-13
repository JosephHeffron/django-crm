from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class NavigationTests(TestCase):
    """Every nav link should point at a real, working (if placeholder)
    page — the nav is only worth as much as its links actually resolve."""

    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")

    def test_dashboard_links_to_every_nav_section(self):
        response = self.client.get(reverse("core:index"))
        for name in [
            "crm:company_list",
            "crm:contact_list",
            "crm:lead_list",
            "crm:deal_list",
            "crm:activity_list",
            "crm:task_list",
            "core:search",
        ]:
            self.assertContains(response, reverse(name))

    def test_each_nav_url_is_reachable_and_login_required(self):
        for name, label in [
            ("crm:company_list", "Companies"),
            ("crm:contact_list", "Contacts"),
            ("crm:lead_list", "Leads"),
            ("crm:deal_list", "Deals"),
            ("crm:activity_list", "Activities"),
            ("crm:task_list", "Tasks"),
            ("core:search", "Search"),
        ]:
            url = reverse(name)

            self.client.logout()
            anon_response = self.client.get(url)
            self.assertEqual(anon_response.status_code, 302, f"{name} should require login")

            self.client.login(username="alice", password="correct-horse-battery")
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"{name} should render")
            self.assertContains(response, label)

    def test_current_nav_section_is_marked_for_orientation(self):
        # Usability review finding: the nav had no way to tell which
        # section you're currently in.
        response = self.client.get(reverse("crm:company_list"))
        self.assertContains(response, 'aria-current="page">Companies')
        self.assertNotContains(response, 'aria-current="page">Contacts')

    def test_dashboard_is_marked_current_on_the_dashboard(self):
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, 'aria-current="page">Dashboard')
