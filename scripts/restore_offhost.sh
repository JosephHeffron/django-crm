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
RESTIC_TAG="${RESTIC_TAG:-django-crm}"

# Must match scripts/backup.sh's own handling exactly — a relative
# local repository path resolves against whatever directory restic
# happens to run from, and that script cd's into $BACKUPS_DIR before
# calling restic while this script runs from $REPO_DIR. Anchoring a
# relative path to $REPO_DIR here (same as backup.sh) keeps both
# scripts pointed at the same repository. Left untouched for an
# already-absolute path or a backend URL (contains ":").
case "$RESTIC_REPOSITORY" in
/* | *:* | "") ;;
*) RESTIC_REPOSITORY="$REPO_DIR/$RESTIC_REPOSITORY" ;;
esac

[ -n "$RESTIC_REPOSITORY" ] || {
	echo "ERROR: RESTIC_REPOSITORY is not set in .env — nothing to restore from." >&2
	echo "This host has no off-host backup destination configured." >&2
	exit 1
}

SNAPSHOT="${1:-latest}"

echo "--- snapshots available in $RESTIC_REPOSITORY ---"
restic snapshots --tag "$RESTIC_TAG"

mkdir -p "$BACKUPS_DIR"

echo "--- restoring snapshot $SNAPSHOT into $BACKUPS_DIR ---"
# scripts/backup.sh pushes each backup as a path relative to
# $BACKUPS_DIR (it cd's there first) — so restoring directly into
# $BACKUPS_DIR recreates backups/<timestamp>/... in place, ready for
# scripts/restore.sh, with no extra directory-hunting needed here.
restic restore "$SNAPSHOT" --tag "$RESTIC_TAG" --target "$BACKUPS_DIR"

echo
echo "=== restored $SNAPSHOT from off-host into $BACKUPS_DIR ==="
echo "Available backups now:"
ls -1 "$BACKUPS_DIR"
echo
echo "Run ./scripts/restore.sh <timestamp> --yes to complete the restore,"
echo "per docs/DISASTER_RECOVERY.md."
