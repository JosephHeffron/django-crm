# ARM64 compatibility review

Phase 9 unit 1 — an ARM64 compatibility audit, per the roadmap and
`docs/ARCHITECTURE.md`'s "ARM64 deployment strategy" (all base images
must support `linux/arm64`; builds are tested via `qemu-user-static` on
the Fedora workstation before ever reaching the physical Raspberry Pi).
Same format as `docs/DATABASE_REVIEW.md`/`docs/SECURITY_REVIEW.md`/
`docs/USABILITY_REVIEW.md`/`docs/PRODUCTION_CONFIG_REVIEW.md`: findings
checked empirically, not assumed from documentation.

## Method

- Confirmed `qemu-user-static` and its `binfmt_misc` handlers (set up in
  Phase 0) are still installed and registered on this workstation —
  the prerequisite for everything else in this review.
- Checked every base image's multi-arch manifest via `skopeo inspect
  --raw` for a `linux/arm64/v8` entry (`caddy:2.11.4-alpine` was
  already confirmed this way during Phase 8 unit 1; re-checked
  `python:3.12-slim` and `postgres:18-alpine` here).
- Checked every pinned Python dependency in `requirements.txt` on PyPI
  for architecture-specific wheels vs. pure-Python (`py3-none-any`)
  ones — the only one with native code is `psycopg2-binary`.
- **Actually built the production `Containerfile` for `linux/arm64`**
  via `podman build --platform linux/arm64`, using this workstation's
  existing qemu emulation — not just confirmed the base images
  individually support the architecture.
- **Actually ran the built ARM64 image** (`podman run --platform
  linux/arm64`) and checked, from inside a live emulated process:
  `uname -m`, the effective user, the Python version, and — the one
  genuinely load-bearing check — that `psycopg2` (the one dependency
  with compiled C code) actually **imports and initializes**
  successfully under emulation, not just that `pip` found a
  filename that claimed to match.

## Findings

### Base images

All three base images this project depends on publish a
`linux/arm64/v8` manifest, confirmed directly against each image's own
multi-arch manifest list (not inferred from Docker Hub's UI or general
reputation):

| Image | Tag | `linux/arm64/v8`? |
|---|---|---|
| `python` | `3.12-slim` | Yes |
| `postgres` | `18-alpine` | Yes |
| `caddy` | `2.11.4-alpine` | Yes (confirmed in Phase 8 unit 1) |

### Python dependencies

| Package | Version | Wheel type |
|---|---|---|
| `Django` | 6.1.1 | `py3-none-any` — pure Python |
| `gunicorn` | 26.2.0 | `py3-none-any` — pure Python |
| `python-dotenv` | 1.2.3 | `py3-none-any` — pure Python |
| `psycopg2-binary` | 2.9.13 | `manylinux_2_27_aarch64`/`manylinux_2_28_aarch64` (and a `musllinux_..._aarch64` variant, not used here) |

`psycopg2-binary` is the only dependency with compiled code, and its
`manylinux` (glibc) `aarch64` wheel matches `python:3.12-slim`'s
Debian (glibc) base correctly — the `musllinux` variant that wheel
listing also offers would be for an Alpine (musl) base, which this
project's `Containerfile` doesn't use, so pip correctly resolves the
`manylinux` one. This is also why the `Containerfile`'s existing
single-stage design (no compiler, no build step — see its own header
comment) still holds on ARM64: the prebuilt wheel installs directly,
same as on amd64.

### Real ARM64 build and run, not just manifest-checking

`podman build --platform linux/arm64 -f Containerfile .` succeeded
end to end under this workstation's `qemu-user-static` emulation —
`pip install` resolved and installed the `aarch64` wheels shown above
with no compilation step, the same `useradd`/`chown`/`USER django`
non-root setup from the amd64 build applied unchanged, and the build
produced a real, taggable image (`localhost/django-crm-arm64:test`,
`podman inspect` confirms `Architecture: arm64`, `Os: linux`, 214 MB —
close to, not identical to, the amd64 build's 184 MB, an expected
architecture-driven size difference, not a defect).

Ran that image (`podman run --platform linux/arm64`) and confirmed,
from inside the live emulated container:

```
$ uname -m
aarch64
$ whoami
django
$ python3 --version
Python 3.12.14
$ python3 -c "import django, psycopg2; print(django.get_version()); print(psycopg2.__version__)"
6.1.1
2.9.13 (dt dec pq3 ext lo64)
```

The `psycopg2` import succeeding is the one check that couldn't be
inferred from manifest/wheel metadata alone — it's the actual
compiled C extension loading and initializing correctly under
emulation, proof the `manylinux_aarch64` wheel is genuinely
ABI-compatible here, not just correctly named.

## Limitations of this review (stated plainly, not glossed over)

- **`qemu-user-static` emulation proves functional correctness, not
  performance.** A build/run succeeding under emulation on this
  workstation's x86_64 CPU says nothing about actual throughput,
  memory pressure, or timing behavior on the Raspberry Pi 5's real
  ARM Cortex-A76 cores — that can only be measured on the physical
  device. No performance claims are made here; none should be inferred
  from this review.
- **No physical Raspberry Pi hardware exists yet** for this project
  (per `docs/PROJECT_STATE.md`'s "Production" section) — this review
  is exactly the workstation-side, pre-hardware check
  `docs/ARCHITECTURE.md`'s "ARM64 deployment strategy" describes
  ("tested... before ever being deployed to the physical Raspberry
  Pi"), not a substitute for eventually testing on real hardware once
  it's acquired.
- This review builds and smoke-tests the `web` image in isolation —
  it doesn't yet run the full `db`+`web`+`caddy` stack under ARM64
  emulation (migrations, `collectstatic`, a real HTTP round trip
  through gunicorn). That fuller, scripted, repeatable validation is
  Phase 9 unit 2's job (`docs/ARM64_TESTING.md`), not duplicated here.

## Recommendation

No compatibility blockers found. Every base image and every pinned
dependency this project uses already supports `linux/arm64/v8`, and a
real ARM64 build of the production image — including the one
dependency with compiled code — was built and run successfully under
emulation, not just checked on paper. Proceed to Phase 9 unit 2: a
fuller, repeatable ARM64 validation procedure covering the complete
stack (migrations, static files, a real served page), and eventually
real Raspberry Pi hardware once available.
