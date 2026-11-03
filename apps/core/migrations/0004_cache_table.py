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


def drop_cache_table(apps, schema_editor):
    # `DROP TABLE IF EXISTS`, not an unguarded drop: a database that
    # never reached this migration's forward step still has to be able
    # to reverse past it.
    schema_editor.execute(f"DROP TABLE IF EXISTS {schema_editor.quote_name(TABLE)}")


class Migration(migrations.Migration):
    dependencies = [("core", "0003_revenue_goal_label")]

    operations = [migrations.RunPython(create_cache_table, drop_cache_table)]
