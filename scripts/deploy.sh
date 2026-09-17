#!/bin/sh
# Production deployment script, per docs/ARCHITECTURE.md's "Production
# deployment architecture" and CLAUDE.md's DEPLOYMENT RULES: scripted,
# non-destructive, reviewable, with a documented rollback path. Never
# runs automatically — always requires an explicit human invocation
# naming a specific git revision.
#
# Runs ON the production host (the Raspberry Pi), inside the
# deployment user's checkout (~/django-crm, matching
# systemd/crm.service's WorkingDirectory=%h/django-crm) — not on the
# dev workstation. Drives podman-compose directly rather than through
# systemd/crm.service — see restart_and_verify's comment below for
# why. That unit still does its own real job (starting the stack on
# boot); this script just doesn't route through it.
#
# Usage:
#   ./scripts/deploy.sh <git-ref>   # deploy a specific tag/branch/commit
#   ./scripts/deploy.sh rollback    # roll back to the previously-deployed revision
#   ./scripts/deploy.sh status      # report current health without changing anything
#
# <git-ref> should normally be a tag or exact commit SHA, not a moving
# branch name — production should always deploy a pinned, known
# revision. A branch name still works (resolved via origin/<ref>) but
# is not the recommended day-to-day usage.
#
# SERVICE (used only for the informational line in `status`) and
# COMPOSE_FILE can be overridden via environment variables for testing
# against a throwaway compose file without touching the real
# production one (both default to the real values below) — e.g.
#   SERVICE=crm-test.service COMPOSE_FILE=compose.dev.yml ./scripts/deploy.sh <ref>
set -e

SERVICE="${SERVICE:-crm.service}"
COMPOSE_FILE="${COMPOSE_FILE:-compose.prod.yml}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE_FILE="$REPO_DIR/.deploy-last-good-ref"
# How long to wait for containers to report healthy after a restart,
# before treating the deploy as failed. Generous: a real deploy
# rebuilds the web image first (see build_images below), so by the
# time we restart, only container startup — not a build — is being
# timed here.
HEALTH_CHECK_RETRIES=60
HEALTH_CHECK_INTERVAL=5

cd "$REPO_DIR"

usage() {
	echo "Usage: $0 <git-ref>|rollback|status" >&2
	exit 1
}

[ $# -eq 1 ] || usage

require_clean_tree() {
	# Never silently discard operator or in-progress state — this
	# script only ever deploys a clean, fully-committed git ref.
	if ! git diff --quiet || ! git diff --cached --quiet; then
		echo "ERROR: uncommitted changes in $REPO_DIR — refusing to deploy." >&2
		echo "Commit, stash, or discard them first." >&2
		exit 1
	fi
}

verify_health() {
	# Deliberately does NOT check `systemctl is-active`. A
	# Type=oneshot/RemainAfterExit=yes unit's "active" state only ever
	# reflects "ExecStart last exited 0" — systemd never actually
	# tracks whether the containers it started are still alive
	# afterward. Confirmed live: containers died outside of any
	# ExecStop (see restart_and_verify's comment) while systemd still
	# reported the unit "active (exited)" the whole time — a
	# systemctl-based check would have called that healthy. Podman's
	# own per-container Health.Status is the only signal here that
	# actually reflects reality, so it's the only thing checked.
	for name in django-crm_db_1 django-crm_web_1; do
		status=$(podman inspect "$name" --format '{{.State.Health.Status}}' 2>/dev/null || echo "missing")
		if [ "$status" != "healthy" ]; then
			echo "not healthy: $name is '$status'"
			return 1
		fi
	done
	echo "healthy: db and web containers healthy"
}

wait_for_health() {
	i=0
	until verify_health >/dev/null 2>&1; do
		i=$((i + 1))
		if [ "$i" -gt "$HEALTH_CHECK_RETRIES" ]; then
			return 1
		fi
		sleep "$HEALTH_CHECK_INTERVAL"
	done
	return 0
}

build_images() {
	echo "--- building web image, pulling db/caddy images ---"
	podman-compose -f "$COMPOSE_FILE" build web
	podman-compose -f "$COMPOSE_FILE" pull db caddy
}

restart_and_verify() {
	# Migrations run automatically here, not as a separate step:
	# scripts/entrypoint.sh already runs `migrate`/`collectstatic`
	# every time the web container starts (with `set -e`, so a failed
	# migration stops the container rather than starting gunicorn
	# against a half-migrated database) — duplicating that logic in
	# this script would just be a second place for it to drift out of
	# sync.
	# Deliberately drives podman-compose directly rather than going
	# through `systemctl {restart,stop,start} $SERVICE`. Three real,
	# live-confirmed problems ruled that out, all stemming from the
	# same root cause — a Type=oneshot/RemainAfterExit=yes unit's
	# "active" state is systemd's belief about whether ExecStart last
	# exited 0, not a live view of whether the containers it started
	# are still running:
	#   1. `systemctl restart` alone reuses an already-existing
	#      container as-is (even a crashed one) instead of recreating
	#      it from the image just rebuilt above — a deploy could
	#      silently never pick up the new image at all.
	#   2. `systemctl stop` on a unit already in `failed` state (e.g.
	#      after a prior timed-out start) is a no-op — it does not run
	#      ExecStop — so old containers never actually get removed.
	#      Confirmed via `podman inspect <container> --format
	#      '{{.Image}}'` showing an hours-stale image ID after a
	#      "successful" stop. This is precisely the state a rollback
	#      runs in, right after a failed deploy — not an edge case.
	#   3. `systemctl start` on a unit systemd already believes is
	#      `active` (RemainAfterExit=yes) is *also* a no-op, even if
	#      the containers underneath were separately torn down (e.g.
	#      by (1) or (2), or by anything else outside systemd's own
	#      ExecStop) — confirmed live: containers were gone
	#      (`podman ps -a` empty) while `systemctl status` still
	#      reported the unit "active (exited)" from a much earlier,
	#      unrelated start.
	# Calling `podman-compose down`/`up -d` directly sidesteps all
	# three: it's idempotent, doesn't depend on systemd's belief about
	# prior state, and is the same pair of commands this project has
	# relied on and verified throughout every prior compose-related
	# phase. The systemd unit itself is untouched by this and still
	# does its real job — starting the stack on boot (see
	# systemd/crm.service, Phase 10 unit 1) — deploy.sh just doesn't
	# route through it for its own internal orchestration.
	echo "--- tearing down any existing containers ---"
	podman-compose -f "$COMPOSE_FILE" down || true
	echo "--- starting the stack ---"
	# `podman-compose up -d` itself can hang indefinitely, not just
	# time out cleanly: caddy's `depends_on: web: condition:
	# service_healthy` (both compose files) makes podman-compose wait
	# for web to actually pass its healthcheck before it will even
	# attempt to start caddy — and if web never becomes healthy (a
	# genuinely broken deploy, the exact case that matters most here),
	# `up -d` just blocks forever with no timeout of its own. Confirmed
	# live: it sat blocked for over 20 minutes against a deliberately
	# broken commit. `timeout` bounds it — a timeout here isn't
	# treated as fatal, since the health-check loop below is the real
	# arbiter of success or failure either way; it just stops `up -d`
	# itself from being the thing that hangs.
	timeout 300 podman-compose -f "$COMPOSE_FILE" up -d ||
		echo "podman-compose up -d did not finish within 300s — proceeding to the health check, which will correctly detect and report failure"

	echo "--- waiting for containers to report healthy ---"
	if wait_for_health; then
		verify_health
		return 0
	fi
	verify_health || true
	return 1
}

deploy_ref() {
	ref="$1"
	require_clean_tree
	previous="$(git rev-parse HEAD)"

	echo "--- deploying $ref (currently at $previous) ---"
	git fetch origin
	# Try origin/<ref> first (covers branch names — always fresh off
	# the fetch above, never a stale local branch pointer), falling
	# back to $ref directly (covers tags and commit SHAs, which have
	# no origin/ prefix). --detach: deploying a pinned revision, not
	# tracking a branch.
	git checkout --detach "origin/$ref" 2>/dev/null || git checkout --detach "$ref"
	resolved="$(git rev-parse HEAD)"
	echo "checked out $resolved"

	build_images

	if restart_and_verify; then
		echo "$previous" >"$STATE_FILE"
		echo "=== deployed $ref ($resolved) successfully — previous ref ($previous) saved for rollback ==="
		return 0
	fi

	echo "Deployment of $ref FAILED health check — rolling back to $previous" >&2
	git checkout --detach "$previous"
	build_images
	if restart_and_verify; then
		echo "Rolled back to $previous successfully. Investigate $ref before retrying." >&2
	else
		echo "ERROR: rollback to $previous ALSO failed health check — manual intervention required." >&2
	fi
	exit 1
}

rollback() {
	[ -f "$STATE_FILE" ] || {
		echo "ERROR: no recorded previous ref ($STATE_FILE not found) — nothing to roll back to." >&2
		exit 1
	}
	require_clean_tree
	previous="$(cat "$STATE_FILE")"
	echo "--- rolling back to $previous ---"
	git checkout --detach "$previous"
	build_images
	if restart_and_verify; then
		echo "=== rolled back to $previous successfully ==="
	else
		echo "ERROR: rollback to $previous failed health check — manual intervention required." >&2
		exit 1
	fi
}

status() {
	echo "current revision: $(git rev-parse HEAD)"
	if [ -f "$STATE_FILE" ]; then
		echo "last-good (rollback target): $(cat "$STATE_FILE")"
	fi
	# Informational only, not authoritative — see verify_health's
	# comment on why a oneshot unit's "active" state can't be trusted
	# to reflect real container health.
	if systemctl --user is-active --quiet "$SERVICE" 2>/dev/null; then
		echo "$SERVICE (boot-time unit): active"
	else
		echo "$SERVICE (boot-time unit): not active"
	fi
	verify_health
}

case "$1" in
rollback) rollback ;;
status) status ;;
*) deploy_ref "$1" ;;
esac
