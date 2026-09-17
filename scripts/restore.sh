#!/bin/sh
# Disaster recovery restore script, per docs/ARCHITECTURE.md's "Backup
# strategy" and docs/DISASTER_RECOVERY.md. Restores a backup produced
# by scripts/backup.sh — models a real disaster (the current
# postgres_data/media_files/caddy_data/caddy_config state is assumed
# lost or untrustworthy) by discarding those volumes entirely and
# rebuilding them from the backup, not by restoring "over" whatever is
# currently there.
#
# This is a genuinely destructive operation — it removes the current
# database and volumes. Per CLAUDE.md's DATABASE SAFETY rules, it:
#   - refuses to run without an explicit --yes flag
#   - always takes a fresh backup of current state first (via
#     scripts/backup.sh), so a mistaken restore still has a way back
#   - never touches the live .env — the backup's env.backup is
#     extracted next to it for manual review/diff, never auto-applied,
#     since the live .env may hold newer or different real secrets
#     than whatever the backup captured
#
# Usage: ./scripts/restore.sh <backup-timestamp> --yes
#   <backup-timestamp> names a directory under backups/ (as produced
#   by scripts/backup.sh), e.g. 2026-09-17T03-00-00Z.
#
# SERVICE_PREFIX and COMPOSE_FILE can be overridden via environment
# variables for testing against a throwaway stack, matching
# scripts/backup.sh and scripts/deploy.sh.
set -e

COMPOSE_FILE="${COMPOSE_FILE:-compose.prod.yml}"
SERVICE_PREFIX="${SERVICE_PREFIX:-django-crm}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUPS_DIR="$REPO_DIR/backups"
DB_CONTAINER="${SERVICE_PREFIX}_db_1"
HEALTH_CHECK_RETRIES=60
HEALTH_CHECK_INTERVAL=5

cd "$REPO_DIR"

usage() {
	echo "Usage: $0 <backup-timestamp> --yes" >&2
	echo "Available backups:" >&2
	# Redirection order matters: >&2 first (send stdout to the
	# terminal's current stderr) THEN 2>/dev/null (hide ls's own error
	# messages) — the reverse order sends both streams to /dev/null,
	# silently discarding the listing entirely. Confirmed live: got an
	# empty "Available backups:" section with the order swapped.
	ls -1 "$BACKUPS_DIR" >&2 2>/dev/null || echo "  (none found in $BACKUPS_DIR)" >&2
	exit 1
}

[ $# -eq 2 ] && [ "$2" = "--yes" ] || usage

TIMESTAMP="$1"
SRC="$BACKUPS_DIR/$TIMESTAMP"

[ -d "$SRC" ] || {
	echo "ERROR: no backup found at $SRC" >&2
	usage
}
for f in db.dump media_files.tar caddy_data.tar caddy_config.tar; do
	[ -f "$SRC/$f" ] || {
		echo "ERROR: $SRC is missing $f — not a complete backup, refusing to restore from it." >&2
		exit 1
	}
done

# Stage the backup outside backups/ before touching anything else, and
# restore from the staged copy ($SRC) from here on — the original
# ($ORIGINAL_SRC) is kept only for display. Restoring later takes its
# own safety backup (see below), whose retention pruning runs against
# everything in backups/ — including the backup being restored from,
# if it happens to be old enough to fall past the retention window
# once the new safety backup is counted. Confirmed live: restoring
# from a backup old enough to sit right at the retention boundary let
# the safety backup's own pruning delete it out from under the
# restore, after the stack was already torn down. Staging a copy
# removes any dependency on the original still existing once the
# safety backup runs.
ORIGINAL_SRC="$SRC"
SRC="$(mktemp -d)"
trap 'rm -rf "$SRC"' EXIT
cp -a "$ORIGINAL_SRC/." "$SRC/"

echo "=== RESTORING from $ORIGINAL_SRC ==="
echo "This will DESTROY the current database and media/Caddy volumes"
echo "and replace them with the contents of this backup."
echo

verify_health() {
	# Same reasoning as scripts/deploy.sh: check podman's own
	# per-container Health.Status directly, not systemctl — see that
	# script's comments for why systemctl's view of a Type=oneshot
	# unit can't be trusted to reflect real container state.
	for name in "${SERVICE_PREFIX}_db_1" "${SERVICE_PREFIX}_web_1"; do
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

# Best-effort, not mandatory: in a genuine disaster (the case this
# script exists for), the current db container may already be gone —
# nothing left to back up. Confirmed live: an earlier version of this
# script unconditionally required the safety backup to succeed, which
# meant it refused to run at all in exactly the worst-case scenario it
# was meant to help with — a total loss with nothing left to protect
# against being overwritten. Only skip it when there's genuinely
# nothing there; if the container exists but the backup still fails
# for some other reason, that's still a hard stop.
if podman container exists "$DB_CONTAINER" 2>/dev/null; then
	echo "--- taking a safety backup of current state before restoring ---"
	COMPOSE_FILE="$COMPOSE_FILE" SERVICE_PREFIX="$SERVICE_PREFIX" "$REPO_DIR/scripts/backup.sh" || {
		echo "ERROR: pre-restore safety backup failed — refusing to proceed with a destructive restore" >&2
		echo "without one. Investigate why the safety backup failed first." >&2
		exit 1
	}
else
	echo "--- no current $DB_CONTAINER found — nothing to back up, proceeding directly to restore ---"
fi

echo "--- tearing down the current stack ---"
podman-compose -f "$COMPOSE_FILE" down || true

echo "--- removing current database and volumes (data is being replaced from the backup) ---"
for vol in postgres_data media_files caddy_data caddy_config; do
	podman volume rm "${SERVICE_PREFIX}_${vol}" 2>/dev/null || true
done

echo "--- recreating volumes from the backup ---"
for vol in media_files caddy_data caddy_config; do
	podman volume create "${SERVICE_PREFIX}_${vol}" >/dev/null
	podman volume import "${SERVICE_PREFIX}_${vol}" "$SRC/${vol}.tar"
done
# postgres_data is NOT imported from a volume tar — pg_dump/pg_restore
# is the mechanism here (see docs/ARCHITECTURE.md's "logical dumps"
# decision), so this volume is left for the db container's own
# from-empty initialization below, then populated via pg_restore.
podman volume create "${SERVICE_PREFIX}_postgres_data" >/dev/null

echo "--- starting db only, so it can initialize an empty database first ---"
timeout 300 podman-compose -f "$COMPOSE_FILE" up -d db ||
	echo "db did not become ready within 300s — proceeding to the health check, which will correctly detect and report failure"
i=0
until podman exec "$DB_CONTAINER" sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
	i=$((i + 1))
	if [ "$i" -gt "$HEALTH_CHECK_RETRIES" ]; then
		echo "ERROR: db never became ready — cannot restore into it." >&2
		exit 1
	fi
	sleep "$HEALTH_CHECK_INTERVAL"
done

echo "--- restoring database from backup ---"
podman cp "$SRC/db.dump" "$DB_CONTAINER:/tmp/restore.dump"
podman exec "$DB_CONTAINER" sh -c 'pg_restore --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/restore.dump'
podman exec "$DB_CONTAINER" rm -f /tmp/restore.dump

echo "--- starting the full stack ---"
timeout 300 podman-compose -f "$COMPOSE_FILE" up -d ||
	echo "podman-compose up -d did not finish within 300s — proceeding to the health check, which will correctly detect and report failure"

echo "--- waiting for containers to report healthy ---"
if wait_for_health; then
	verify_health
else
	verify_health || true
	echo "ERROR: restored stack failed its health check — investigate before considering this restore complete." >&2
	exit 1
fi

# .env is deliberately never auto-applied — extracted alongside the
# restored data for the operator to manually review/diff against the
# live .env, which may hold newer or different real secrets. Named to
# end in .backup (not .restored) so it's covered by the existing
# *.backup gitignore pattern without needing a second one.
cp "$SRC/env.backup" "$REPO_DIR/env.restored.backup"
chmod 600 "$REPO_DIR/env.restored.backup"
echo
echo "=== restore from $ORIGINAL_SRC complete ==="
echo "The backup's .env was extracted to env.restored.backup for your"
echo "own review — it was NOT applied. Diff it against the live .env"
echo "by hand and merge anything relevant yourself."
