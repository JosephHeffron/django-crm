#!/bin/sh
# Classifies a change by the files it touches, for the two places that
# can take a shortcut when only the public website changed: CI
# (.github/workflows/ci.yml) and `scripts/deploy.sh --website-only`.
# One rule, one copy, so the two can never disagree about what counts
# (docs/decisions/0017-the-website-lives-in-this-repository.md).
#
# Reads changed paths on stdin, one per line — the output of
# `git diff --name-only --no-renames A B`. Prints exactly one word:
#
#   website   every path is under website/, and none under website/partials/
#   full      anything else, including no paths at all
#
# website/partials/ is never a shortcut: Django reads those files for
# the /book/ page (ADR 0017), so a change there can break the CRM's own
# rendering and needs the full suite and an image rebuild. Everything
# outside website/ — code, the Caddyfile, compose files, workflows,
# requirements — is full by definition.
#
# Callers must pass --no-renames to git diff: without it, a file moved
# from apps/ into website/ lists only its new path, and the deletion
# outside website/ would go unseen.
#
# Reads all of its input before answering, rather than exiting at the
# first non-website path, so the writer on the other end of the pipe is
# never killed by SIGPIPE — under `set -o pipefail` (GitHub Actions'
# default bash) that would fail the step instead of answering `full`.
set -eu

scope=""
while IFS= read -r path || [ -n "$path" ]; do
	case "$path" in
	"") ;;
	website/partials/*) scope=full ;;
	website/*) [ -n "$scope" ] || scope=website ;;
	*) scope=full ;;
	esac
done

echo "${scope:-full}"
