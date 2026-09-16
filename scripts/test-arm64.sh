#!/bin/sh
# Repeatable ARM64 cross-architecture validation, per
# docs/ARM64_TESTING.md and docs/ARCHITECTURE.md's "ARM64 deployment
# strategy". Builds the production image for linux/arm64 and runs the
# full db+web+caddy stack under this workstation's qemu-user-static
# emulation (Phase 0), proving migrations, collectstatic, and a real
# served page all work on the target architecture — not just that the
# base images claim arm64 support (docs/ARM64_REVIEW.md, Phase 9 unit
# 1, already covers that).
#
# Usage: ./scripts/test-arm64.sh
# Requires: podman, qemu-user-static with binfmt_misc handlers
# registered (already set up on this workstation since Phase 0).
#
# Uses throwaway container/network names and a throwaway database — no
# real .env, no real data, nothing this touches is meant to survive
# the run. Safe to re-run any time.
set -e

NET=arm64-test-net
DB=arm64-test-db
WEB=arm64-test-web
CADDY=arm64-test-caddy
IMAGE=django-crm-arm64:test
WEB_PORT=18000
CADDY_PORT=18443

# --platform linux/arm64 on `podman pull`/`podman build` overwrites the
# *shared* local tag for that image (postgres:18-alpine,
# caddy:2.11.4-alpine) with the arm64 variant — discovered the hard way
# while writing this script: it silently left this workstation's real
# dev/prod compose stacks pointing at arm64 images. Restoring the
# native amd64 tags afterward is therefore not optional cleanup, it's
# a correctness requirement for this script to be safe to run — hence
# unconditional in the trap, not skippable, and run every time
# regardless of how the script exits.
cleanup() {
	echo "--- cleanup ---"
	podman rm -f "$CADDY" "$WEB" "$DB" >/dev/null 2>&1 || true
	podman network rm "$NET" >/dev/null 2>&1 || true
	podman rmi "$IMAGE" >/dev/null 2>&1 || true
	echo "Restoring native amd64 tags for postgres/caddy (this run's"
	echo "--platform linux/arm64 pulls overwrite the shared local tag):"
	podman pull --platform linux/amd64 docker.io/library/postgres:18-alpine
	podman pull --platform linux/amd64 docker.io/library/caddy:2.11.4-alpine
	podman image prune -f >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "--- building production image for linux/arm64 ---"
podman build --platform linux/arm64 -t "$IMAGE" -f Containerfile .

echo "--- starting throwaway network + db ---"
podman network create "$NET" >/dev/null
podman run -d --name "$DB" --platform linux/arm64 --network "$NET" \
	-e POSTGRES_DB=arm64test -e POSTGRES_USER=arm64test -e POSTGRES_PASSWORD=arm64test \
	docker.io/library/postgres:18-alpine >/dev/null

echo "--- waiting for db to be ready ---"
until podman exec "$DB" pg_isready -U arm64test -d arm64test >/dev/null 2>&1; do
	sleep 2
done
echo "db ready ($(podman exec "$DB" uname -m))"

echo "--- starting web (runs migrate + collectstatic via entrypoint.sh, then gunicorn) ---"
# --network-alias web: Caddyfile.dev's reverse_proxy target is the
# hardcoded hostname "web" (matching compose.dev.yml's service name) —
# aliasing this container to that name lets caddy's config work
# unmodified against a plain `podman run` setup, not just compose.
podman run -d --name "$WEB" --platform linux/arm64 --network "$NET" --network-alias web \
	-p "${WEB_PORT}:8000" \
	-e DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" \
	-e DJANGO_ALLOWED_HOSTS=localhost \
	-e DJANGO_CSRF_TRUSTED_ORIGINS=https://localhost \
	-e POSTGRES_DB=arm64test -e POSTGRES_USER=arm64test -e POSTGRES_PASSWORD=arm64test \
	-e POSTGRES_HOST="$DB" -e POSTGRES_PORT=5432 \
	"$IMAGE" >/dev/null

echo "--- waiting for web to become healthy ---"
i=0
until curl -s -o /dev/null "http://localhost:${WEB_PORT}/accounts/login/"; do
	i=$((i + 1))
	if [ "$i" -gt 30 ]; then
		echo "web never became reachable — check: podman logs $WEB"
		exit 1
	fi
	sleep 2
done
echo "web ready ($(podman exec "$WEB" uname -m))"

echo "--- verifying migrations + collectstatic actually ran (web's own startup log) ---"
podman logs "$WEB" 2>&1 | grep -q "Running migrations" || {
	echo "FAIL: no migration output in web's logs"
	exit 1
}
podman logs "$WEB" 2>&1 | grep -q "static files copied" || {
	echo "FAIL: no collectstatic output in web's logs"
	exit 1
}
echo "migrations + collectstatic confirmed"

echo "--- verifying a real page renders via gunicorn directly ---"
TITLE=$(curl -s -H "X-Forwarded-Proto: https" "http://localhost:${WEB_PORT}/accounts/login/" | grep -o "<title>.*</title>")
[ "$TITLE" = "<title>Log in</title>" ] || {
	echo "FAIL: unexpected page title: $TITLE"
	exit 1
}
echo "gunicorn served a real page: $TITLE"

echo "--- adding caddy and verifying the full proxied path ---"
podman run -d --name "$CADDY" --platform linux/arm64 --network "$NET" \
	-p "${CADDY_PORT}:443" \
	-v "$(pwd)/Caddyfile.dev:/etc/caddy/Caddyfile:ro,Z" \
	docker.io/library/caddy:2.11.4-alpine >/dev/null

i=0
until curl -sk -o /dev/null "https://localhost:${CADDY_PORT}/accounts/login/"; do
	i=$((i + 1))
	if [ "$i" -gt 30 ]; then
		echo "caddy never became reachable — check: podman logs $CADDY"
		exit 1
	fi
	sleep 2
done
echo "caddy ready ($(podman exec "$CADDY" uname -m))"

TITLE=$(curl -sk "https://localhost:${CADDY_PORT}/accounts/login/" | grep -o "<title>.*</title>")
[ "$TITLE" = "<title>Log in</title>" ] || {
	echo "FAIL: unexpected page title through caddy: $TITLE"
	exit 1
}
echo "full db+web+caddy stack served a real page through the proxy: $TITLE"

echo
echo "=== ARM64 cross-architecture validation PASSED ==="
