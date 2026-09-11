2026-09-10
ACTION: Added scram-sha-256 host auth rules for the django_crm role/database
COMMAND: edited /var/lib/pgsql/data/pg_hba.conf, then
         sudo -u postgres psql -c "SELECT pg_reload_conf();"
PURPOSE: The system PostgreSQL install defaults local TCP connections
         (127.0.0.1/32, ::1/128) to ident auth, which rejects the
         password-based auth Django's DATABASES setting uses. Added two
         scoped rules (host django_crm django_crm 127.0.0.1/32
         scram-sha-256, and the ::1/128 equivalent) above the generic
         ident rule, rather than loosening auth for all databases/roles.
RESULT: SUCCESS — verified with a direct psycopg2 connection using the
        django_crm role and .env credentials.
