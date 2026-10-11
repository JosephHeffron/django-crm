"""Lead and Deal are gone from the code and still in the database.

Phase 18 unit 5. Phase 17 folded every Lead into a Contact and every
Deal into a Quote; this retired the two models. The decision was to
remove the code and keep the tables, so `crm/0011` is state-only: it
changes no schema at all.

That combination is easy to half-undo by accident, in either direction
— a later migration quietly dropping a table, or an import of a model
that no longer exists — so each half is checked here rather than
assumed.
"""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase
from django.urls import reverse

from apps.crm.tests._helpers import grant_role
from apps.crm.undo import UNDOABLE_MODELS

User = get_user_model()
PASSWORD = "correct-horse-battery"


class TheCodeIsGoneTests(TestCase):
    def test_django_no_longer_knows_either_model(self):
        names = {model.__name__ for model in apps.get_app_config("crm").get_models()}
        self.assertNotIn("Lead", names)
        self.assertNotIn("Deal", names)

    def test_nothing_points_at_a_lead_or_a_deal_any_more(self):
        """The three pointer fields are off the models they were on."""
        for model_name, field_names in (("Task", ["deal"]), ("Activity", ["lead", "deal"])):
            model = apps.get_model("crm", model_name)
            present = {field.name for field in model._meta.get_fields()}
            for field_name in field_names:
                self.assertNotIn(field_name, present, f"{model_name}.{field_name}")

    def test_undo_will_not_touch_them(self):
        self.assertNotIn(("crm", "lead"), UNDOABLE_MODELS)
        self.assertNotIn(("crm", "deal"), UNDOABLE_MODELS)


class TheDataIsStillThereTests(TestCase):
    """The owner chose to keep the tables. Nothing may quietly drop them."""

    def columns(self, table):
        with connection.cursor() as cursor:
            cursor.execute(
                "select column_name from information_schema.columns where table_name = %s",
                [table],
            )
            return {row[0] for row in cursor.fetchall()}

    def test_both_tables_still_exist(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "select table_name from information_schema.tables "
                "where table_name in ('crm_lead', 'crm_deal')"
            )
            self.assertEqual({row[0] for row in cursor.fetchall()}, {"crm_lead", "crm_deal"})

    def test_the_pointer_columns_still_exist(self):
        """Dropping these was drafted and abandoned; see `crm/0011`.

        `jobs/0003`'s fold reads `crm_task.deal_id`, so the column has
        to outlive the model for the Phase 17 rollback to work at all.
        """
        self.assertIn("deal_id", self.columns("crm_task"))
        self.assertLessEqual({"lead_id", "deal_id"}, self.columns("crm_activity"))

    def test_the_retirement_migration_runs_no_sql(self):
        """State-only, proved from the migration rather than its docstring."""
        migration = MigrationLoader(None).disk_migrations[("crm", "0011_retire_lead_and_deal")]
        for operation in migration.operations:
            self.assertEqual(
                getattr(operation, "database_operations", []),
                [],
                f"{operation} would change the database",
            )


class MigrationOrderTests(TestCase):
    """The hazard that broke every fresh database build once already.

    An earlier draft of `crm/0011` dropped `crm_task.deal_id`, which
    `jobs/0003`'s fold reads. Nothing in the graph ordered the two, and
    Django's topological sort happened to put the retirement first, so
    the fold failed with "column deal_id does not exist" on any database
    built from scratch — the CI test database included. The drop is
    gone; the ordering is pinned so the hazard cannot return.
    """

    def test_the_fold_is_applied_before_the_retirement(self):
        plan = MigrationLoader(None).graph.forwards_plan(("crm", "0011_retire_lead_and_deal"))
        self.assertIn(("jobs", "0003_fold_leads_and_deals"), plan)
        self.assertLess(
            plan.index(("jobs", "0003_fold_leads_and_deals")),
            plan.index(("crm", "0011_retire_lead_and_deal")),
        )


class OldLinksStillLandSomewhereUsefulTests(TestCase):
    """Both lists were in the menu for most of this project's life."""

    def setUp(self):
        user = User.objects.create_user("alice", password=PASSWORD)
        grant_role(user)
        self.client.login(username="alice", password=PASSWORD)

    def test_the_leads_list_redirects_to_customers(self):
        response = self.client.get("/leads/")
        self.assertRedirects(
            response, reverse("crm:contact_list"), status_code=301, target_status_code=200
        )

    def test_the_deals_list_redirects_to_estimates(self):
        response = self.client.get("/deals/")
        self.assertRedirects(
            response, reverse("jobs:quote_list"), status_code=301, target_status_code=200
        )

    def test_a_bookmarked_lead_or_deal_page_is_simply_gone(self):
        """No row to point at, so a redirect would be a lie."""
        for url in ("/leads/1/", "/deals/1/", "/leads/add/", "/deals/add/"):
            self.assertEqual(self.client.get(url).status_code, 404, url)
