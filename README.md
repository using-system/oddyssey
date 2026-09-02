# oddyssey

https://github.com/user-attachments/assets/776b98b0-862d-4865-b8f1-568e6710c228

**A CLI toolbox for Observability-Driven Development (ODD).**

[![CI](https://github.com/using-system/oddyssey/actions/workflows/ci-mcp-server.yml/badge.svg?event=pull_request)](https://github.com/using-system/oddyssey/actions/workflows/ci-mcp-server.yml)
[![PyPI](https://img.shields.io/pypi/v/oddyssey-mcp)](https://pypi.org/project/oddyssey-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Install

### With APM (every CLI)

With [APM](https://microsoft.github.io/apm/), for Claude Code:

```bash
uvx --from 'apm-cli==0.28.0' apm install --global --target claude using-system/oddyssey
```

Same command for every other supported CLI agent — swap the target:
`--target opencode`, `copilot`, `kiro`, `cursor`, `codex`, `gemini`,
`windsurf`. Drop `--global` to install into the current repository
only.

Keep the `apm-cli==0.28.0` pin — it is the minimum supported version
and the one CI validates the package with (bumped together). Older
apm-cli releases (0.14.x observed) predate `targets:` support and
corrupt the install: the payload fans out to targets that were never
requested, `.mcp.json` is emptied on uninstall, and the manifest can
be left invalid.

To update an existing install to the latest version:

```bash
uvx --from 'apm-cli==0.28.0' apm update --global --target claude using-system/oddyssey
```

It shows the update plan and asks for confirmation (`--yes` to skip,
`--dry-run` to only look); `uvx --from 'apm-cli==0.28.0' apm outdated`
tells you whether an update is worth running.

### From the native marketplaces (no APM)

**Claude Code**

```
/plugin marketplace add using-system/oddyssey
/plugin install oddyssey@oddyssey-plugin
```

**GitHub Copilot CLI**

```
copilot plugin marketplace add using-system/oddyssey
copilot plugin install oddyssey@oddyssey-plugin
```

**Kimi Code**

```
/plugin marketplace add using-system/oddyssey
/plugin install oddyssey@oddyssey-plugin
```

**Codex** — this repository publishes the Codex manifest at
`.agents/plugins/marketplace.json`; add the repository as a plugin
source in your Codex plugins settings.

The native artifacts are generated from the APM package on every
release (`marketplace/`, built by `scripts/build-marketplace.sh`) and
carry the same agents, commands, skills, and pinned MCP server. The
other CLIs (opencode, Cursor, Windsurf, Kiro, Gemini) install via APM
above.

## The idea

ODD complements Spec-Driven Development: observe a running service — local
or remote — through its telemetry, turn what you see into the next SDD wave
(spec, plan, implement), then observe again. A continuous improvement loop,
indefinitely.

Everything is built on OpenTelemetry. For **local** observation, the MCP
server pilots a complete Grafana stack (UI, traces, metrics, logs,
profiles) that agents use to observe and fix. For **remote** stacks,
observation works against Grafana or any other OpenTelemetry backend
(Datadog, Dynatrace, Azure Monitor, CloudWatch, Splunk, ...).

oddyssey provides:

- **an OpenTelemetry expert** ([`otel-instrumentation-expert`](.apm/agents/otel-instrumentation-expert.agent.md))
  that investigates your stack and hands your CLI agent everything needed
  to integrate OpenTelemetry and deploy collectors;
- **a run investigation agent** ([`observe-run`](.apm/agents/observe-run.agent.md)),
  local or remote, that delivers a complete observation report your CLI
  agent turns into a spec-driven plan of fixes and improvements;
- **a complete local observability stack** based on Grafana, piloted by
  the oddyssey MCP server;
- **an ODD memory carried by the repo itself** — every observation and
  instrumentation report lands in `.odd/`, committed and versioned with
  the code, shared with the whole team, and recalled as the baseline of
  the next run: the loop accumulates knowledge instead of starting
  blind.

Everything is packaged for any coding agent
([APM](https://microsoft.github.io/apm/): Claude Code, Copilot, Cursor,
Codex, Gemini, and friends).

## How to

The loop in three prompts — every example below links to a real artifact
from this repository: oddyssey instrumented, observed, and verified its
own MCP server.

**Step 1 — Instrument OpenTelemetry.**

```text
/odd-instrument-otel add OpenTelemetry to my project XXX
```

The `otel-instrumentation-expert` agent investigates the codebase,
stores its report in `.odd/otel-instrumentation-reports/` (committed —
the next investigation starts from it), and hands back everything a
spec-driven wave needs. Real output of that wave on this repo: the
[design spec](docs/superpowers/specs/2026-08-22-mcp-otel-instrumentation-design.md)
and the
[implementation plan](docs/superpowers/plans/2026-08-22-mcp-otel-instrumentation.md)
generated with [superpowers](https://github.com/obra/superpowers) from
the agent's investigation report.

**Step 2 — Observe a local run.**

```text
/odd-observe check that my project XXX starts and answers requests on the /user endpoint
```

The `observe-run` agent drives the run, queries the telemetry, and
stores its report in `.odd/observe-run-reports/` — findings, evidence,
and the replay protocol the verification will consume. Real example: the
[first observation report](.odd/observe-run-reports/2026-08-22-2154-mcp-otel-instrumentation-verification.md)
(4 confirmed findings) and the
[fix-wave plan](docs/superpowers/plans/2026-08-23-mcp-otel-fix-wave.md)
the next SDD wave built from it.

**Step 3 — Verify the fixes the SDD wave delivered.**

```text
/odd-verify check that report XXX from .odd has been fixed
```

The same agent replays the stored report's protocol and rules on every
recorded item — before-value, after-value, pass criterion. Real example:
the
[verification report](.odd/observe-run-reports/2026-08-22-2227-verify-mcp-otel-instrumentation-verification.md)
— 9/9 checks pass, all 4 findings fixed, measured not assumed.

**Step 4 — Deploy and observe remotely.**

Let the deployment run for a while first — a remote observation needs
real traffic history to read, not a freshly booted service. Then point
the missions at the remote stack: **its CLI must be configured
beforehand** (gcx for a Grafana stack), and `/odd-config` is the
guided way to switch and prove the connection before any mission runs.

```text
/odd-config switch to grafana
/odd-observe what did my service XXX do over the last 24 hours?
```

Or in a single prompt — naming the stack in the mission switches the
configuration too:

```text
/odd-observe what did my service XXX do over the last 24 hours on my stack grafana?
```

The backends oddyssey manages, their associated CLI, and their switch
prompt are documented in
[docs/guide/backends.md](docs/guide/backends.md).

And the loop starts again: an SDD wave from the remote observation, a
local observe, a verify — and on it goes. Every step left a committed
report in `.odd/`; their formats — frontmatter fields, allowed values,
body structure — are documented in
[docs/guide/reports.md](docs/guide/reports.md).

### Miscellaneous prompts

#### /odd-status

```text
/odd-status
/odd-status where is the loop for my service XXX
/odd-status what was observed on prod for my service XXX
/odd-status wontfix F4 of my last XXX report - port-move is rare, 14.5s accepted
```

Answers "where is the loop?" from the committed `.odd/` history and git
alone — no backend queries, no report written. Renders per-service loop
state (last observation, last verification and its verdict, the
observed → fixed → verified chain), the findings ledger as a burn-down,
trends across runs from the stored numbers, telemetry gaps not yet
closed, and a next recommended action (verify, observe, or rest) that
cites its inputs. Optionally scope it to a service, a stack, or an
environment: `/odd-status checkout on local`.

It also **declines findings**: a finding no verification ever ruled on
stays open forever, however deliberately you decided to live with it.
Ask for the decision — in the arguments as above, or as a follow-up
once the status is rendered — with a rationale, and it lands as one
appended row in `.odd/decisions.md`, the committed ledger next to the
reports; that file is committed on its own, and the reports themselves
are never edited. The status then re-renders the finding as
**declined**, with its verdict, date, and rationale, counted apart from
the fixed ones. Reversing a decision (`/odd-status reopen F4: ...`) is
a new row, so the history of the decision stays readable.

#### /odd-instrument-bench

```text
/odd-instrument-bench author a load benchmark for my service XXX, p95 under 300ms
/odd-instrument-bench stress test XXX against http://localhost:8080, error rate must stay under 1%
/odd-instrument-bench update the XXX-read-heavy benchmark - the cart endpoints moved
```

Authors a k6 load-test benchmark for a service — a script plus a
manifest — as reviewed code under `.odd/benchmarks/<name>/`, through
the `k6-benchmark-expert` agent. The prompt first asks back whatever
only you can decide (test type, thresholds, target environment, new
benchmark or an update to an existing one) and proposes a load shape
and duration for you to confirm; the agent discovers the rest — which
endpoints matter, what the stored `.odd/` reports already say about the
service. It checks your thresholds against the floors in the service's
own code (a fixed delay, an injected error rate) and hands an
unattainable one back with the evidence rather than persisting it: you
raise, drop, re-scope, or keep it knowingly. It validates what it wrote
(`k6 inspect`, one smoke iteration at the target, asked for first when
the target is remote) and **never runs it as a benchmark**. Run the
stored benchmark through `/odd-observe` (`/odd-observe run
.odd/benchmarks/<name>/`): the `observe-run` agent drives the script
unmodified through the `run-scenario` skill and rules on the
manifest's thresholds from the service's own telemetry, k6's summary
recorded as evidence only. The full lifecycle, and what a benchmark is
versus a report, are in
[docs/guide/benchmarks.md](docs/guide/benchmarks.md).

More invocation examples for every prompt live in
[docs/guide/prompts.md](docs/guide/prompts.md).

## The ODD principles

- **The system must be observable locally.** Prefer a docker-compose
  that starts your whole stack, and mocks for the remote systems it
  queries — the oddyssey MCP server provides the local observability
  backend the telemetry lands in.
- **Instrument with the expert.** Bring OpenTelemetry into your
  services through the `otel-instrumentation-expert` agent rather than
  by hand.
- **One design loop, always the same.** Every feature follows: SDD to
  develop it → observe a local run → fix and improve → repeat those
  last two steps until satisfied. Then deploy to the target
  environments. After some time, run a remote observation on the
  deployed environment's stack to seed the next SDD wave — and the
  loop starts again from the local run.
- **Maturity spaces observation out.** The time between remote
  observations grows as the service matures: a young service gets
  observed often, a stable one only when something is worth learning.
- **Evidence over impressions.** Every claim about a service comes from
  a query and its result — numbers, trace IDs, log lines — never "it
  seems faster".
- **Cross-confirm before concluding.** Never conclude from one signal
  what two could confirm (traces, metrics, logs, profiles); a
  single-signal anomaly is always labeled as such.
- **The memory lives with the code.** Observation reports are stored in
  the observed repo under `.odd/` — version that directory (do not add
  it to `.gitignore`): the reports get reviewed in PRs, shared by the
  whole team, and the git history reads observed → fixed → verified.
- **Verify by replaying, not by re-measuring differently.** A fix is
  proven by replaying the recorded scenario identically; one changed
  variable invalidates the before/after comparison.
- **What's missing is a finding too.** Telemetry gaps — absent spans,
  logs without trace IDs, missing histograms — are deliverables of the
  observation and feed the next instrumentation wave.
- **One telemetry, two consumers.** The metrics, traces, and logs do not
  serve ODD alone: the same data feeds classic runtime observability —
  dashboards, alerting, incident investigation. Instrument once, and the
  development loop and the operation of the system read from the same
  source of truth.
- **Agents observe, they never fix.** The investigation agents only
  observe and report — they never modify the code directly. Their report
  is a universal input: feed it to any spec-driven framework for the
  spec-and-implement wave, turn it into JIRA tickets, or hand it to a
  human — what happens next stays your call.

## Prerequisites

- **[Docker](https://docs.docker.com/get-docker/)** — runs the local
  observability stack (the MCP server drives it directly).
- **[gcx](https://github.com/grafana/gcx)** — required only when observing
  a **Grafana** backend (the local stack, self-hosted, or Grafana Cloud):
  `brew install gcx`, or
  `curl -fsSL https://raw.githubusercontent.com/grafana/gcx/main/scripts/install.sh | sh`.
- **Other backends** need their own CLI, each covered by the
  [`observability-cli-guides`](.apm/skills/observability-cli-guides/SKILL.md)
  skill: Datadog ([Pup](https://github.com/DataDog/pup)), Dynatrace
  ([dtctl](https://github.com/dynatrace-oss/dtctl)), Azure Monitor
  (`az`), AWS CloudWatch/X-Ray (`aws`), Splunk (`splunk`).
- **[k6](https://grafana.com/docs/k6/latest/set-up/install-k6/)** —
  needed to author a benchmark and to run one: `/odd-instrument-bench`
  validates the script it writes with `k6 inspect` and one smoke
  iteration (never a benchmark run), and `/odd-observe` and
  `/odd-verify` run it. The three prompts' preflights install it on
  the spot when it is missing and Homebrew is available
  (`brew install k6`, no confirmation — k6 needs no account and no
  configuration); without Homebrew they follow the platform's
  non-interactive path when one exists, otherwise hand you the
  official steps. To install it yourself: `brew install k6` on macOS,
  the official APT/YUM repositories or a release binary on Linux, the
  MSI installer or a package manager on Windows — a `k6` on your path,
  which the `grafana/k6` Docker image does not provide.

## The MCP server

One job: **pilot a local Grafana stack with an OpenTelemetry endpoint**.
One container ([grafana/otel-lgtm](https://github.com/grafana/docker-otel-lgtm),
pinned, its definition embedded in the server — Docker is the only
prerequisite) exposes Grafana on `:3000`, OTLP on `:4317`/`:4318`, and
Pyroscope's ingest on `:4040` (profiles are pushed there directly by
pyroscope-io-style SDKs — they are not an OTLP signal); apps export
their telemetry there. Tempo traces, Prometheus metrics, Loki
logs, and Pyroscope profiles are all queried through the Grafana proxy
(`:3000/api/datasources/proxy/uid/...`), so the same paths work against any
Grafana; on remote stacks the backend behind it can be something other
than the local otel-lgtm container.

| Tool | What it does | Params |
| --- | --- | --- |
| `odd_stack_up` | Start the local stack and wait until it is ready | `env` (optional) — container environment; applies at creation only, is persisted in `stack_config.local` (credential-named variables excluded) and reapplied on every recreation |
| `odd_stack_down` | Destroy it — stored telemetry does not survive | — |
| `odd_stack_status` | Probe whether it is up — and get the container's identity too: `image`, `created`/`started` timestamps, and its user-set `env` (credential-named values redacted to `null`; all four `null` when there is no container) | — |
| `odd_stack_reset` | Wipe all stored telemetry and return a fresh, ready stack — the next run starts from a clean slate | `env` (optional) — always applies, the container is recreated; persisted/reapplied like `odd_stack_up` |
| `odd_config_get` | Read the global configuration — stack backend and local host ports | — |
| `odd_config_set` | Update it — a port change resets the stack so the new value applies right away | `config` — partial merge, e.g. `{"local": {"grafana_port": 3300}}`; inside `stack_config`, `null` deletes a key or a stack's entry |

The server is instrumented with OpenTelemetry and, by default, exports its
own traces and metrics to the local stack (`http://localhost:4318`, OTLP
`http/protobuf` — the protocol is fixed, `OTEL_EXPORTER_OTLP_PROTOCOL` set
to anything else is not honored). Any `OTEL_*` variable set in the MCP
client's env block overrides the defaults, and `OTEL_SDK_DISABLED=true`
turns telemetry off entirely. When the stack is down, telemetry is silently
dropped — the normal state, and never a failure of the server.

## The agents and skills

The loop: **investigate** (agents) → **spec & implement** (the main
agent's spec-driven workflow) → **observe again** — telemetry on both
ends. Each observation report is stored in the observed repo
(`.odd/observe-run-reports/`), versioned by git and shared with the whole
team, and becomes the baseline the next run diffs against — the loop
accumulates knowledge instead of starting blind.

Every prompt, agent, and skill of the package — its role, and who
invokes what across them and the MCP tools — is listed in
[docs/guide/dependencies.md](docs/guide/dependencies.md).

## Development

The exact build, test, and lint commands live in
[CONTRIBUTING.md](CONTRIBUTING.md) — single source, matching what CI
enforces. In short: the project under `src/` is a self-contained uv
project (own `pyproject.toml`); `tests/` mirrors `src/`.

## Contributing

Issues, docs fixes, and code are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md) for the layout, the exact build/test
commands, and the PR conventions (squash titles drive the released
version). Questions and ideas belong in
[Discussions](https://github.com/using-system/oddyssey/discussions);
[good first issues](https://github.com/using-system/oddyssey/issues?q=is%3Aopen+label%3A%22good+first+issue%22)
are waiting.

## License

[MIT](LICENSE)
