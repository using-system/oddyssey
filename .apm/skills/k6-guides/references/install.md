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

## Ensure k6 is present - auto-install

The criterion for installing a CLI rather than offering it: no
account, no credentials, no tenant behind it. The backend CLIs (`aws`,
`az`, `gcx` against a remote instance, ...) are offered and never
installed silently (`update-backend-configuration`'s rule), because
each is tied to an account, credentials, and a tenant the user must
set up regardless - the install is one step of a setup only they can
finish. k6 has none of that: no account, no login, no configuration
file - the binary existing is the entire setup, the same reasoning
`setup-local-stack` applies to a missing gcx on the self-serve local
stack ("install it if missing"), the one other CLI this package
installs itself. So a missing k6 is a step to run, not a stop to
report:

1. **Detect** - `command -v k6`. Present: done, cite `k6 version`.
2. **Homebrew available** (`command -v brew` - macOS, Linuxbrew) - run
   `brew install k6` directly, no confirmation asked, then re-detect
   and cite `k6 version`. Verified live (2026-09-02, macOS arm64):
   after `brew uninstall k6`, `brew install k6` restored `k6 v2.2.0`
   from the core-tap bottle in under two seconds - a leaf formula, no
   dependencies, no configuration touched.
3. **No Homebrew** - fetch the official page (`set-up/install-k6/.md`)
   and follow the platform's path only where it completes without
   interaction; anything that prompts for confirmation or elevation
   is a hand-back, not an auto-install. On Windows the page names
   `winget` (manifests created by the community) and `choco` (an
   **unofficial** package, the page's own word) - prefer `winget`, pass
   the manager's non-interactive flags (`--accept-source-agreements
   --accept-package-agreements` for winget, `-y` for choco), and treat
   a UAC or agreement prompt as the hand-back above; the official
   Windows route the page also offers, the MSI installer, is
   interactive and goes to the user. The Linux package paths
   (Debian/Ubuntu APT, Fedora/CentOS DNF) all require `sudo` and a
   repository key: surface those steps to the user verbatim from the
   fetched page rather than running them, and say k6 is still
   missing. The `grafana/k6` Docker image is an option to offer the
   user, never a substitute the agent switches to - it puts no `k6` on
   the path and changes the command shape (`k6 run -` reads the
   script from stdin, no local filesystem) every stored benchmark and
   record assumes.
4. **Say what happened** - "auto-installed" only when a step above
   genuinely completed without interaction; otherwise the exact steps
   left to the user.

**Who runs it.** Whoever is in the main conversation, where the
install command is visible as it runs: the three prompts' preflights
(`/odd-instrument-bench`, `/odd-observe`, `/odd-verify`), or
`run-scenario` itself when its stored-benchmark step is entered
directly there, without a prompt. Inside a subagent - `observe-run`
running `run-scenario`, `k6-benchmark-expert`'s validation step -
nothing installs: a binary still missing there means the preflight did
not run, a contract failure to report, never a reason to install from
a subagent.

## Who needs k6 installed

**Both sides.** `k6-benchmark-expert` needs it to **validate** what it
writes - `k6 inspect` and the one-iteration smoke (running-tests.md,
"Validating without running") - without ever running the benchmark;
`run-scenario`'s stored-benchmark step (its section 6, reached from
`/odd-observe` or `/odd-verify` in `drive` mode with a `benchmark`)
needs it to **run** one. The `/odd-instrument-bench`, `/odd-observe`,
and `/odd-verify` preflights ensure it is present before dispatching
(the auto-install step above); the subagent-side steps fail fast when
it is still absent - never approximating the script with other
tooling, never installing from a subagent. This project's README
Prerequisites section lists k6 on those terms: needed to author (to
validate) and to run a benchmark, installed on the spot when missing
and Homebrew is available; authoring never runs one.
