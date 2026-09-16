# Production image. No multi-stage build: psycopg2-binary ships a
# self-contained wheel (bundles libpq), so nothing here needs a C
# compiler or system Postgres client headers — a single stage is
# genuinely sufficient, not a shortcut (CLAUDE.md's "do not
# overengineer" rule).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# Installed before the rest of the app is copied in, so this layer is
# only rebuilt when requirements.txt actually changes, not on every
# code change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x scripts/entrypoint.sh \
    && useradd --create-home --uid 1000 django \
    && chown -R django:django /app
USER django

EXPOSE 8000

ENTRYPOINT ["scripts/entrypoint.sh"]
# 3 workers is a modest, explicit starting point for a Raspberry Pi 5
# (4 cores) — not computed from CPU count, which would be needless
# complexity for a single, known deployment target. Logs to
# stdout/stderr rather than a file, since the container runtime is
# what owns log capture here.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]
