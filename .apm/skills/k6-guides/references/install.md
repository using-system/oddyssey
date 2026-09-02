# Install & detect k6

Official docs: https://grafana.com/docs/k6/latest/set-up/install-k6/
Raw markdown via `.md` suffix or `Accept: text/markdown` (verified 2026-08).

**This guide targets k6 v2** (confirmed `k6 v2.2.0` on 2026-08-31).
k6 v2 removed the `externally-controlled` executor, the
`k6 pause/resume/scale/status` commands, and `k6 login`, and moved the
Go module import path - never suggest any of those. See
[migrating-to-v2](https://grafana.com/docs/k6/latest/get-started/migrating-to-v2/)
if a script or command predates v2.

## Binary

- **Binary**: `k6`
- **Detect**: `command -v k6` - `k6 version` on success prints
  `k6 vX.Y.Z (commit/..., go..., <os>/<arch>)`.
- **Install**:
  - macOS: `brew install k6` (verified 2026-08: installs from the core
    Homebrew tap, no separate tap needed - `k6 v2.2.0` on Homebrew as of
    this writing).
  - Linux: the official APT/YUM repositories, or a static binary from
    the [releases page](https://github.com/grafana/k6/releases).
  - Docker: `grafana/k6` image, e.g.
    `docker run --rm -i grafana/k6 run - <script.js`.
  - Full platform matrix: `set-up/install-k6` (fetch for anything beyond
    macOS/Linux/Docker - Windows, package-manager specifics change
    between k6 releases, don't guess).

## Who needs k6 installed

**Not `k6-benchmark-expert`.** Authoring a benchmark never runs it - the
agent writes a script and a manifest, it does not execute `k6 run`.
Installation matters on the **execution** side: `run-scenario`'s
stored-benchmark step (its section 6, reached from `/odd-observe` or
`/odd-verify` in `drive` mode with a `benchmark`) runs `k6 run` and
must fail fast with the install steps above when the binary is absent -
never approximating the script with other tooling, never installing
silently. The `/odd-observe` and `/odd-verify` preflights check the
binary before dispatching a drive mission with a benchmark, so the
missing-k6 case is reported in the main conversation where the user can
act on it. This project's README Prerequisites section lists k6 on
exactly those terms: needed to **run** a benchmark, never to author one.
