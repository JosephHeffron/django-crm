# PHASE 09: ARM64 COMPATIBILITY REVIEW (UNIT 1)

Started: 2026-09-16
Ended: 2026-09-16

## Objective

First of (at least) two Phase 9 units, per the roadmap: an ARM64
compatibility audit (`docs/ARM64_REVIEW.md`), matching
`docs/ARCHITECTURE.md`'s "ARM64 deployment strategy" — all base images
must support `linux/arm64`, builds tested via `qemu-user-static` on
this Fedora workstation before ever reaching the physical Raspberry
Pi.

## Files created / changed

- `docs/ARM64_REVIEW.md` — new. Full findings write-up (see below).

## Commands

$ `rpm -q qemu-user-static` / `which qemu-aarch64-static` / `ls
  /proc/sys/fs/binfmt_misc/`
Result: already installed and registered (Phase 0 setup) — `qemu-
aarch64` present among the registered `binfmt_misc` handlers.

$ `skopeo inspect --raw` against each base image's multi-arch manifest
  list, checked for a `linux/arm64/v8` entry:
  - `python:3.12-slim` — present.
  - `postgres:18-alpine` — present.
  - `caddy:2.11.4-alpine` — already confirmed during Phase 8 unit 1,
    not re-run.

$ PyPI JSON API checked for each pinned dependency in
  `requirements.txt`:
  - `Django==6.1.1`, `gunicorn==26.2.0`, `python-dotenv==1.2.3` — all
    ship only a `py3-none-any` wheel (pure Python, architecture-
    agnostic).
  - `psycopg2-binary==2.9.13` — ships `manylinux_2_27_aarch64`/
    `manylinux_2_28_aarch64` wheels for cp312 (matching
    `python:3.12-slim`'s glibc/Debian base) alongside a separate
    `musllinux` variant not applicable here.

$ `podman build --platform linux/arm64 -t django-crm-arm64:test -f
  Containerfile .`
Result: **succeeded end to end** under this workstation's qemu
emulation — `pip install` resolved and installed the `aarch64` wheels
above with no compilation step (confirming the `Containerfile`'s
existing single-stage, no-compiler design still holds on ARM64), the
same non-root `useradd`/`USER django` setup applied unchanged.
`podman inspect` confirmed `Architecture: arm64`, `Os: linux`, 214 MB
(vs. 184 MB for the amd64 build — an expected architecture-driven
difference, not a defect).

$ `podman run --platform linux/arm64 --entrypoint sh
  localhost/django-crm-arm64:test -c "whoami; uname -m; python3
  --version"`
Result: `django` / `aarch64` / `Python 3.12.14` — confirms the image
is genuinely running as ARM64 under emulation, not just tagged as one.

$ `podman run --platform linux/arm64 ... python3 -c "import django,
  psycopg2; print(django.get_version()); print(psycopg2.__version__)"`
Result: `6.1.1` / `2.9.13 (dt dec pq3 ext lo64)` — **the one check that
couldn't be inferred from manifest/wheel metadata alone**: the
compiled C extension in `psycopg2-binary`'s `manylinux_aarch64` wheel
actually loads and initializes correctly under emulation, proof of
real ABI compatibility, not just a correctly-named filename.

$ `podman rmi localhost/django-crm-arm64:test`
Result: throwaway test image removed after use.

$ `ruff check .` / `ruff format --check .` / `bandit -r apps config
  -q` / `pip-audit` / `manage.py check`
Result: PASS — pre-existing B106 test-fixture findings only from
bandit (unrelated, same baseline as every prior unit this session).

$ `python manage.py test` (full suite)
Result: PASS — 296 tests (unchanged — this unit is a review doc, no
application code).

## Tests

`python manage.py test` — 296 passed, 0 failures.

## Decisions

- Scoped this unit to the compatibility audit alone (manifest checks
  plus a build-and-smoke-test of the `web` image in isolation), not
  the fuller functional validation (migrations, `collectstatic`, a
  real served page, the full 3-container stack under emulation) —
  that's explicitly Phase 9 unit 2's job
  (`docs/ARM64_TESTING.md`), kept separate rather than blurring the
  two deliverables together.
- Stated the emulation-vs-real-hardware limitation explicitly in the
  review doc itself, not just in this log — `qemu-user-static` proves
  functional correctness, not performance, and no physical Raspberry
  Pi exists yet for this project to validate against. Didn't want a
  future reader of `docs/ARM64_REVIEW.md` alone to come away thinking
  more was proven than actually was.

## Errors

None. No compatibility blockers were found for any base image or
dependency — this unit's live build-and-run proof came back clean on
the first attempt.

## Lessons learned

- Checking a dependency's wheel *filename* on PyPI confirms intent,
  not correctness — actually importing the compiled module inside a
  running emulated process is what confirms the wheel is truly
  ABI-compatible. Worth doing for any future dependency with compiled
  code, not just trusting a `manylinux_aarch64` tag at face value.
- `qemu-user-static`/`binfmt_misc` set up once during Phase 0 paid off
  directly here with zero additional setup — a good example of
  front-loaded environment work saving a later phase real effort.

## Git

Branch: `feature/arm64-review`
Commit: `1d78b2e`
Merged to `main`: `9bc4727` (regular merge commit, PR #58 — CI green:
`test` + `dependency-audit` both pass; the repo is private now, so
Sourcery doesn't review it — expected, not an error, and this unit's
own live build-and-run verification already served as the equivalent
scrutiny)

## Next

Phase 9 unit 2 — ARM64 image build + repeatable cross-architecture
validation (`docs/ARM64_TESTING.md`): the fuller functional test this
unit deliberately deferred — migrations, `collectstatic`, a real
served page, ideally the full `db`+`web`+`caddy` stack under ARM64
emulation, packaged as a repeatable procedure. Phase 9 is not yet
complete — `docs/ROADMAP.md` stays unchecked until unit 2 also merges.
