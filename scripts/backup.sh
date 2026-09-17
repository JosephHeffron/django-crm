#!/bin/sh
# Production backup script, per docs/ARCHITECTURE.md's "Backup
# strategy": scheduled logical PostgreSQL dumps (pg_dump), stored
# outside the database container, plus media files and configuration
# (.env, Caddy certificates/config) — "equally required for recovery"
# per that same section — with a retention policy.
#
# Runs ON the production host, inside the deployment user's checkout
# (matching scripts/deploy.sh). Safe to run at any time: takes a
# consistent pg_dump snapshot of a live database (no downtime, no
# stopping any container) and read-only volume exports.
#
# Usage: ./scripts/backup.sh
# Output: backups/<timestamp>/{db.dump,media_files.tar,caddy_data.tar,
#         caddy_config.tar,env.backup,manifest.txt}
#
# SERVICE_PREFIX and COMPOSE_FILE can be overridden via environment
# variables for testing against a throwaway stack without touching
# production — e.g.
#   SERVICE_PREFIX=django-crm COMPOSE_FILE=compose.dev.yml VOLUME_SUFFIX=_dev ./scripts/backup.sh
# VOLUME_SUFFIX must match compose.dev.yml's own volume naming
# (media_files_dev, caddy_data_dev, caddy_config_dev, postgres_data_dev
# — added in Phase 7 so compose.dev.yml's stack never shares volumes
# with compose.prod.yml's on the same host) when testing against that
# file — compose.prod.yml's volumes carry no suffix, so it defaults to
# empty. Confirmed live during Phase 13 unit 2's clean-environment
# test: without this, pointing COMPOSE_FILE at compose.dev.yml (the
# header's own original example, before this was found) silently
# backed up the *wrong*, nonexistent volumes — no error, no warning,
# "backup complete" reported anyway, with genuinely empty
# media_files.tar/caddy_data.tar/caddy_config.tar.
# BACKUP_RETENTION_COUNT controls how many past backups to keep
# (default 7 — roughly a week of daily backups).
set -e

COMPOSE_FILE="${COMPOSE_FILE:-compose.prod.yml}"
SERVICE_PREFIX="${SERVICE_PREFIX:-django-crm}"
VOLUME_SUFFIX="${VOLUME_SUFFIX:-}"
BACKUP_RETENTION_COUNT="${BACKUP_RETENTION_COUNT:-7}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUPS_DIR="$REPO_DIR/backups"
DB_CONTAINER="${SERVICE_PREFIX}_db_1"

cd "$REPO_DIR"

TIMESTAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
DEST="$BACKUPS_DIR/$TIMESTAMP"
mkdir -p "$DEST"
echo "--- backing up to $DEST ---"

# If anything below fails partway (set -e exits immediately), don't
# leave a partial, misleading backup directory behind — e.g. a
# `db.dump` file that's actually truncated/corrupt because pg_dump
# itself errored mid-write. A failed backup should leave no backup at
# all, not one that looks superficially present. Cleared right before
# the final success message.
trap 'echo "Backup FAILED — removing incomplete backup directory $DEST" >&2; rm -rf "$DEST"' EXIT

# Custom format (-Fc), not plain SQL: compressed, and restorable with
# pg_restore's selective/parallel options — the same reasoning
# docs/ARCHITECTURE.md's "logical dumps" already commits to. Runs
# inside the container over its default local Unix-socket connection
# (trusted by the official postgres image for local connections, the
# same mechanism the compose healthcheck's pg_isready already relies
# on) — no password needs to cross the podman exec boundary.
# $POSTGRES_USER/$POSTGRES_DB come from the container's own
# environment (already set via compose's env_file: .env on the `db`
# service), not re-read from .env here.
echo "--- pg_dump ---"
podman exec "$DB_CONTAINER" sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >"$DEST/db.dump"

# media_files/caddy_data/caddy_config are named Podman volumes, not
# host directories (see compose.prod.yml) — `podman volume export`
# tars a volume's current contents directly, no throwaway container
# needed. static_files is deliberately NOT backed up: it's entirely
# regenerable from source via collectstatic, not user data.
#
# `podman volume exists` is checked explicitly first, rather than
# trusting `podman volume export`'s own exit code to catch a wrong
# volume name — confirmed live that on this project's podman version,
# exporting a name that doesn't appear in `podman volume ls` can still
# exit 0 and silently produce a small, empty-looking tar, rather than
# failing loudly the way a nonexistent name normally would. That's
# exactly how the VOLUME_SUFFIX bug above first surfaced: the backup
# "succeeded" with no error while quietly backing up nothing.
for vol in media_files caddy_data caddy_config; do
	fullname="${SERVICE_PREFIX}_${vol}${VOLUME_SUFFIX}"
	echo "--- exporting volume $fullname ---"
	podman volume exists "$fullname" || {
		echo "ERROR: volume $fullname does not exist — wrong SERVICE_PREFIX/VOLUME_SUFFIX?" >&2
		exit 1
	}
	podman volume export "$fullname" -o "$DEST/${vol}.tar"
done

# .env holds real secrets — copied with restrictive permissions, and
# NOT included in the retention-pruned count logic differently from
# anything else here: the whole timestamped directory is one unit,
# pruned or kept together (see below).
echo "--- copying .env ---"
cp .env "$DEST/env.backup"
chmod 600 "$DEST/env.backup"

{
	echo "Backup taken: $TIMESTAMP"
	echo "Git revision: $(git rev-parse HEAD)"
	echo "Compose file: $COMPOSE_FILE"
	echo
	ls -la "$DEST"
} >"$DEST/manifest.txt"

echo "--- applying retention policy (keep last $BACKUP_RETENTION_COUNT) ---"
# shellcheck disable=SC2012
ls -1d "$BACKUPS_DIR"/*/ 2>/dev/null | sort -r | tail -n "+$((BACKUP_RETENTION_COUNT + 1))" | while read -r old; do
	echo "removing old backup: $old"
	rm -rf "$old"
done

trap - EXIT
echo "=== backup complete: $DEST ==="
