from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Job, Quote
from apps.jobs.tests import _factories as f
from apps.users.models import get_profile
from apps.users.roles import Role, roles_for
from apps.users.stats import crew_stats, sales_stats

PASSWORD = "correct-horse-battery"


def completed(job, days_ago=5, rating=None):
    Job.objects.filter(pk=job.pk).update(
        status=Job.Status.COMPLETED,
        completed_at=timezone.now() - timedelta(days=days_ago),
        customer_rating=rating,
    )


class StatsTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.crew = grant_role(f.user("crew"), Role.CLEANER)
        self.rep = grant_role(f.user("rep"), Role.SALES_REP)
        self.customer = f.contact(self.owner)

    def test_crew_stats(self):
        for price, hours, rating, days_ago in (
            ("100", "2", 5, 5),
            ("300", "4", 4, 20),
            ("999", "9", 1, 200),
        ):
            job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal(price))])
            completed(job, days_ago, rating)
            f.assign(job, self.crew, hours=Decimal(hours))
        upcoming = f.job(self.customer, self.owner, start=timezone.now() + timedelta(days=2))
        f.assign(upcoming, self.crew)

        stats = crew_stats(self.crew, 90)
        self.assertEqual(
            (
                stats["jobs_completed"],
                stats["hours"],
                stats["average_job_value"],
                stats["average_rating"],
            ),
            (2, Decimal("6"), Decimal("200.00"), 4.5),
        )
        self.assertEqual(stats["hours_per_week"], Decimal("0.5"))  # 6 h over 90 days
        self.assertEqual(stats["upcoming"], 1)

    def test_sales_stats(self):
        now = timezone.now()
        won = f.quote(
            self.customer, self.rep, status=Quote.Status.ACCEPTED, accepted_at=now, sent_at=now
        )
        f.quote(self.customer, self.rep, status=Quote.Status.DECLINED, sent_at=now)
        f.quote(self.customer, self.rep, status=Quote.Status.EXPIRED)
        f.quote(self.customer, self.rep, status=Quote.Status.SENT, sent_at=now)
        f.quote(
            self.customer, self.owner, status=Quote.Status.ACCEPTED, accepted_at=now
        )  # not theirs
        Task.objects.create(
            title="Follow up",
            kind=Task.Kind.FOLLOW_UP,
            contact=self.customer,
            service_type=f.service(),
            assigned_to=self.rep,
            created_by=self.rep,
            status=Task.Status.COMPLETED,
            completed_by=self.rep,
            completed_at=now,
        )
        stats = sales_stats(self.rep, 90)
        self.assertEqual(
            (stats["quotes_sent"], stats["won"], stats["decided"], stats["close_rate"]),
            (3, 1, 3, 33),
        )
        self.assertEqual(stats["value_won"], won.total)
        self.assertEqual((stats["follow_ups_completed"], stats["open_quotes"]), (1, 1))

    def test_no_decided_quotes_means_no_close_rate(self):
        self.assertIsNone(sales_stats(self.rep, 30)["close_rate"])


class ProfilePageTests(TestCase):
    def login(self, username, role):
        user = grant_role(f.user(username, first_name=username.title(), last_name="Test"), role)
        self.client.login(username=username, password=PASSWORD)
        return user

    def test_each_role_sees_their_own_kind_of_stats(self):
        for username, role, crew, sales in (
            ("crew", Role.CLEANER, True, False),
            ("rep", Role.SALES_REP, False, True),
            ("boss", Role.OWNER, False, True),
        ):
            self.login(username, role)
            response = self.client.get(reverse("people:profile"), {"days": "30"})
            self.assertEqual(response.status_code, 200, username)
            self.assertEqual(
                (response.context["crew"] is not None, response.context["sales"] is not None),
                (crew, sales),
                username,
            )
            self.assertEqual(response.context["days"], 30)

    def test_title_matching_the_role_is_not_repeated(self):
        user = self.login("rep", Role.SALES_REP)
        profile = get_profile(user)
        profile.title = "Sales Rep"
        profile.save()
        self.assertNotContains(self.client.get(reverse("people:profile")), "Sales Rep · Sales Rep")

    def test_unknown_window_falls_back(self):
        self.login("crew", Role.CLEANER)
        self.assertEqual(
            self.client.get(reverse("people:profile"), {"days": "7"}).context["days"], 90
        )

    def test_edit_own_profile(self):
        user = self.login("crew", Role.CLEANER)
        response = self.client.post(
            reverse("people:profile_edit"),
            {
                "first_name": "Casey",
                "last_name": "Brooks",
                "email": "casey@example.com",
                "title": "Crew lead",
                "phone": "(585) 555-0106",
                "calendar_tone": "6",
            },
        )
        self.assertRedirects(response, reverse("people:profile"))
        user.refresh_from_db()
        profile = get_profile(user)
        self.assertEqual(
            (user.get_full_name(), profile.title, profile.calendar_tone),
            ("Casey Brooks", "Crew lead", 6),
        )

    def test_invalid_edit_saves_nothing(self):
        user = self.login("crew", Role.CLEANER)
        response = self.client.post(
            reverse("people:profile_edit"),
            {"first_name": "X", "email": "not-an-email", "calendar_tone": "6", "title": "Boss"},
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual((user.first_name, get_profile(user).title), ("Crew", ""))


class TeamTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("rep"), Role.SALES_REP)
        self.crew = grant_role(f.user("crew"), Role.CLEANER)
        self.nobody = f.user("nobody")
        self.admin = f.user("admin", is_superuser=True)

    def test_owner_only(self):
        for user, expected in ((self.owner, 200), (self.rep, 403), (self.crew, 403)):
            self.client.login(username=user.username, password=PASSWORD)
            self.assertEqual(self.client.get(reverse("people:team")).status_code, expected)
            self.assertEqual(
                self.client.get(reverse("people:member", args=["crew"])).status_code,
                expected if user != self.crew else 403,
            )

    def test_owner_sees_a_teammates_stats_and_own_page_redirects(self):
        self.client.login(username="boss", password=PASSWORD)
        response = self.client.get(reverse("people:member", args=["crew"]))
        self.assertIsNotNone(response.context["crew"])
        self.assertContains(response, reverse("messaging:direct", args=["crew"]))
        self.assertRedirects(
            self.client.get(reverse("people:member", args=["boss"])), reverse("people:profile")
        )

    def test_roles_for_matches_user_role(self):
        roles = roles_for([self.owner, self.rep, self.crew, self.nobody, self.admin])
        self.assertEqual(
            [roles[u.pk] for u in (self.owner, self.rep, self.crew, self.nobody, self.admin)],
            [Role.OWNER, Role.SALES_REP, Role.CLEANER, None, Role.OWNER],
        )
        self.client.login(username="boss", password=PASSWORD)
        self.assertContains(self.client.get(reverse("people:team")), "No role")
