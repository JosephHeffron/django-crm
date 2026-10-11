#!/bin/sh
# Raise the day's repeat-service follow-ups, per docs/ROADMAP.md's
# Phase 19. Runs `manage.py generate_followups` inside the web
# container, because that is where Django and its dependencies live —
# the host deliberately has no application environment.
#
# Runs ON the production host, inside the deployment user's checkout
# (matching scripts/deploy.sh and scripts/backup.sh). Triggered by
# systemd/crm-followups.timer, not usually by hand.
#
# Usage: ./scripts/followups.sh [--date YYYY-MM-DD]
#
# Safe to run any number of times a day. `apps/crm/followups.py` is
# idempotent by construction: a partial unique constraint allows at
# most one *open* follow-up per customer and service, and a follow-up
# raised since the customer's last job or contact touch suppresses
# another until newer work moves the clock. Running it twice an hour
# apart creates nothing the first run did not.
#
# That idempotence is also why a missed day is not a lost day, which is
# the important difference from scripts/backup.sh. A customer who
# became due yesterday is still due today, so a skipped run raises the
# follow-up a day late rather than never. A missed *backup*, by
# contrast, is a permanent hole.
#
# What is NOT self-correcting is the timer being broken rather than
# skipped — a renamed container, a stack that never came up. Then
# follow-ups stop silently and the only symptom is an absence, which
# nobody notices for weeks. Hence: this exits non-zero on every failure
# path so systemd records it, and it says plainly what to check.
# docs/ADMIN_GUIDE.md has the one-line health check.
#
# SERVICE_PREFIX can be overridden to run against a throwaway stack
# without touching production, the same way backup.sh allows:
#   SERVICE_PREFIX=django-crm ./scripts/followups.sh --date 2026-09-29
set -e

SERVICE_PREFIX="${SERVICE_PREFIX:-django-crm}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WEB_CONTAINER="${WEB_CONTAINER:-${SERVICE_PREFIX}_web_1}"

cd "$REPO_DIR"

# Checked explicitly rather than left to `podman exec` to fail, for the
# same reason backup.sh checks `podman volume exists` first: the
# message a wrong SERVICE_PREFIX produces otherwise is about a missing
# container, not about the setting that caused it.
if ! podman container exists "$WEB_CONTAINER" 2>/dev/null; then
	echo "ERROR: no container named $WEB_CONTAINER." >&2
	echo "Either the stack is not running, or SERVICE_PREFIX is wrong." >&2
	echo "Check: podman ps --format '{{.Names}}'" >&2
	exit 1
fi

echo "--- generating follow-ups in $WEB_CONTAINER ---"
podman exec "$WEB_CONTAINER" python manage.py generate_followups "$@"
echo "=== follow-ups done ==="
