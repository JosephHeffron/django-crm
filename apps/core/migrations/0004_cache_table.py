"""The table behind `CACHES` (ADR 0020).

`createcachetable` is a management command, so the usual instruction is
"run it once by hand after deploying". A migration instead, because the
container entrypoint already runs `migrate` and nothing else in this
project asks the operator to remember a step — and because the test
database then has the table too, so the login rate limit is tested
against the backend it actually uses rather than a locmem stand-in that
would pass while being wrong across workers.

Reversible: dropping the table loses nothing but counters.
"""

from django.core.management import call_command
from django.db import migrations

TABLE = "crm_cache"


def create_cache_table(apps, schema_editor):
    # Quiet: Django's own test runner also creates this table for any
    # DatabaseCache before running the suite, so the command would
    # otherwise print "already exists" on every test run.
    call_command(
        "createcachetable",
        TABLE,
        database=schema_editor.connection.alias,
        verbosity=0,
    )


class Migration(migrations.Migration):
    """Reversible, but the reverse leaves the table standing.

    `CLAUDE.md`'s database-safety rule is "never DROP TABLE" in
    production, and rolling a deployment back is exactly when that rule
    is being leaned on. An empty cache table left behind costs nothing —
    the data in it is counters — while dropping it would be a
    destructive operation performed automatically, which is the thing
    the rule forbids. Dropping it by hand is always available.
    """

    dependencies = [("core", "0003_revenue_goal_label")]

    operations = [migrations.RunPython(create_cache_table, migrations.RunPython.noop)]
