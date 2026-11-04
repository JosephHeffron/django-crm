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


def refuse_to_reverse(apps, schema_editor):
    """Refuse, loudly and with instructions.

    Two things this must not do. It must not **drop the table**:
    `CLAUDE.md`'s database-safety rule is "never DROP TABLE" in
    production, and a rollback is exactly when that rule is being
    leaned on. And it must not **report success** while the table is
    still there, which a no-op reverse does — the migration would be
    marked unapplied while its effect persisted (#200).

    So it stops and says what to do instead. Re-applying is harmless:
    `createcachetable` is idempotent.
    """
    raise RuntimeError(
        "Refusing to reverse: this would mean dropping the crm_cache table, "
        "which CLAUDE.md's database-safety rule forbids doing automatically. "
        "Nothing in it but rate-limit counters. To roll back past this "
        "migration anyway, mark it unapplied without running it — "
        "`manage.py migrate core 0003 --fake` — and drop the table by hand "
        "if you really want it gone. See docs/decisions/0020."
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0003_revenue_goal_label")]

    operations = [migrations.RunPython(create_cache_table, refuse_to_reverse)]
