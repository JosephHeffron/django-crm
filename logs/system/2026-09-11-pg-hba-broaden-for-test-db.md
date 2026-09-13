2026-09-11
ACTION: Broadened the django_crm role's pg_hba.conf auth rule from
        database-scoped (django_crm only) to all databases for that role;
        also granted CREATEDB to the django_crm role.
COMMAND: sudo -u postgres psql -c "ALTER ROLE django_crm CREATEDB;"
         edited /var/lib/pgsql/data/pg_hba.conf (django_crm -> all for
         the django_crm role), then
         sudo -u postgres psql -c "SELECT pg_reload_conf();"
PURPOSE: Django's test runner creates and connects to a separate
         `test_django_crm` database. The original pg_hba.conf rule from
         Phase 1 was scoped to the `django_crm` database by name, so it
         didn't match the test database and fell through to the
         system-default `ident` rule, which rejects password auth.
         CREATEDB was also missing, so the test runner couldn't create
         the test database at all. Still scoped to the `django_crm` role
         specifically (not opened for all roles) — only broadened the
         database-name column to `all`.
RESULT: SUCCESS — `python manage.py test apps.crm` creates
        `test_django_crm` and connects successfully.
