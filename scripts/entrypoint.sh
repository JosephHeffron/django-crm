#!/bin/sh
# Production container entrypoint. Runs migrations and collects static
# files against whatever DATABASE/settings the container was started
# with, then hands off to the container's CMD (gunicorn) — see
# Containerfile. `set -e` so a failed migration stops the container
# instead of starting gunicorn against a half-migrated database.
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
