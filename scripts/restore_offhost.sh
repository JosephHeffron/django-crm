#!/bin/sh
# Pulls a backup down from the off-host restic repository into
# backups/, for the actual disaster docs/BACKUP_DR_AUDIT.md's HIGH
# finding #1 was about: the local backups/ directory lives on the same
# disk as everything else it protects, so if THAT disk is what failed,
# scripts/restore.sh has nothing under backups/ to restore from until
# this runs first. Once this completes, scripts/restore.sh
# <timestamp> --yes proceeds exactly as documented in
# docs/DISASTER_RECOVERY.md — this script only repopulates backups/,
# it does not touch any running container or volume itself.
#
# Usage: ./scripts/restore_offhost.sh [snapshot-id]
#   snapshot-id: a restic snapshot ID, as shown by `restic snapshots`
#   (also printed by this script before restoring). Omit to restore
#   the most recent snapshot ("latest").
#
# Requires RESTIC_REPOSITORY (and RESTIC_PASSWORD, plus whatever
# backend credentials that repository needs) set in .env — see
# .env.example and docs/ADMIN_GUIDE.md's "Backups" section. Requires
# the `restic` binary on this host.
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUPS_DIR="$REPO_DIR/backups"

cd "$REPO_DIR"

if [ -f "$REPO_DIR/.env" ]; then
	set -a
	# shellcheck disable=SC1091
	. "$REPO_DIR/.env"
	set +a
fi

[ -n "$RESTIC_REPOSITORY" ] || {
	echo "ERROR: RESTIC_REPOSITORY is not set in .env — nothing to restore from." >&2
	echo "This host has no off-host backup destination configured." >&2
	exit 1
}

SNAPSHOT="${1:-latest}"

echo "--- snapshots available in $RESTIC_REPOSITORY ---"
restic snapshots --tag django-crm

mkdir -p "$BACKUPS_DIR"

echo "--- restoring snapshot $SNAPSHOT into $BACKUPS_DIR ---"
# scripts/backup.sh pushes each backup as a path relative to
# $BACKUPS_DIR (it cd's there first) — so restoring directly into
# $BACKUPS_DIR recreates backups/<timestamp>/... in place, ready for
# scripts/restore.sh, with no extra directory-hunting needed here.
restic restore "$SNAPSHOT" --tag django-crm --target "$BACKUPS_DIR"

echo
echo "=== restored $SNAPSHOT from off-host into $BACKUPS_DIR ==="
echo "Available backups now:"
ls -1 "$BACKUPS_DIR"
echo
echo "Run ./scripts/restore.sh <timestamp> --yes to complete the restore,"
echo "per docs/DISASTER_RECOVERY.md."
