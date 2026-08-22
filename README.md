# oddyssey

![The oddyssey: coding agents sailing the telemetry sea through the pantheon of observability gods](assets/images/banner.png)

**A CLI toolbox for Observability-Driven Development (ODD).**

## Install

With [APM](https://microsoft.github.io/apm/), for Claude Code:

```bash
uvx --from 'apm-cli==0.28.0' apm install --global --target claude using-system/oddyssey
```

Same command for every other supported CLI agent — swap the target:
`--target opencode`, `copilot`, `kiro`, `cursor`, `codex`, `gemini`,
`windsurf`. Drop `--global` to install into the current repository
only.

## The idea

ODD complements Spec-Driven Development: observe a running service — local
or remote — through its telemetry, turn what you see into the next SDD wave
(spec, plan, implement), then observe again. A continuous improvement loop,
indefinitely.

Everything is built on OpenTelemetry. For **local** observation, the MCP
server pilots a complete Grafana stack (UI, traces, metrics, logs,
profiles) that agents use to observe and fix. For **remote** environments,
observation works against a Grafana stack or any other OpenTelemetry
backend (Datadog, Dynatrace, Azure Monitor, CloudWatch, Splunk, ...).

oddyssey provides:

- **an OpenTelemetry expert** ([`otel-instrumentation-expert`](.apm/agents/otel-instrumentation-expert.agent.md))
  that investigates your stack and hands your CLI agent everything needed
  to integrate OpenTelemetry and deploy collectors;
- **a run investigation agent** ([`observe-run`](.apm/agents/observe-run.agent.md)),
  local or remote, that delivers a complete observation report your CLI
  agent turns into a spec-driven plan of fixes and improvements;
- **a complete local observability stack** based on Grafana, piloted by
  the oddyssey MCP server;
- **persistent run-observation reports** stored in the observed repo
  (`.odd/observe-run-reports/`), versioned with the code and recalled
  as the baseline of the next run.

Everything is packaged for any coding agent
([APM](https://microsoft.github.io/apm/): Claude Code, Copilot, Cursor,
Codex, Gemini, and friends).

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
  environment to seed the next SDD wave — and the loop starts again
  from the local run.
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

## The MCP server

One job: **pilot a local Grafana stack with an OpenTelemetry endpoint**.
One container ([grafana/otel-lgtm](https://github.com/grafana/docker-otel-lgtm),
pinned, its definition embedded in the server — Docker is the only
prerequisite) exposes Grafana on `:3000` and OTLP on `:4317`/`:4318`; apps
export their telemetry there. Tempo traces, Prometheus metrics, Loki
logs, and Pyroscope profiles are all queried through the Grafana proxy
(`:3000/api/datasources/proxy/uid/...`), so the same paths work against any
Grafana; on remote environments the stack behind it can be something other
than the local otel-lgtm container.

| Tool | What it does |
| --- | --- |
| `odd_stack_up` | Start the local stack and wait until it is ready |
| `odd_stack_down` | Destroy it — stored telemetry does not survive |
| `odd_stack_status` | Probe whether it is up |
| `odd_stack_reset` | Wipe all stored telemetry and return a fresh, ready stack — the next run starts from a clean slate |

The server is instrumented with OpenTelemetry and, by default, exports its
own traces and metrics to the local stack (`http://localhost:4318`, OTLP
`http/protobuf` — the protocol is fixed, `OTEL_EXPORTER_OTLP_PROTOCOL` set
to anything else is not honored). Any `OTEL_*` variable set in the MCP
client's env block overrides the defaults, and `OTEL_SDK_DISABLED=true`
turns telemetry off entirely. When the stack is down, telemetry is silently
dropped — the normal state, and never a failure of the server.

## The agents and skills

| Primitive | Role |
| --- | --- |
| [`otel-instrumentation-expert`](.apm/agents/otel-instrumentation-expert.agent.md) (agent) | Investigate a codebase and hand back every input for a spec-driven plan to implement OpenTelemetry: stack inventory, per-service approach sourced from the official docs, open decisions, verification protocol |
| [`observe-run`](.apm/agents/observe-run.agent.md) (agent) | Observe a running service — on the local stack or any remote backend — through its telemetry (metrics, traces, logs, profiles) and hand back every input for a spec-driven plan of fixes and improvements |
| [`otel-guides`](.apm/skills/otel-guides/SKILL.md) (skill) | Curated map of the official OpenTelemetry docs: every supported language plus the cross-language guides (SDK configuration, semantic conventions, Collector deployment) |
| [`setup-local-stack`](.apm/skills/setup-local-stack/SKILL.md) (skill) | Configure gcx against the local stack without touching the user's contexts, with the datasource UIDs and the push-model caveats |
| [`observability-cli-guides`](.apm/skills/observability-cli-guides/SKILL.md) (skill) | Curated map of every major backend's terminal query surface: Grafana (gcx), Datadog (Pup), Dynatrace (dtctl), Azure Monitor (az), CloudWatch (aws), Splunk |
| [`run-scenario`](.apm/skills/run-scenario/SKILL.md) (skill) | Drive a reproducible request scenario against a local service and record it verbatim, so the same numbers are measurable before a fix and after it |
| [`create-observe-run-report`](.apm/skills/create-observe-run-report/SKILL.md) (skill) | The ODD loop's memory: persist each observation report into the observed repo (`.odd/observe-run-reports/`) and recall the previous ones as the next run's baseline |
| [`/odd-observe`](.apm/prompts/odd-observe.prompt.md) (prompt) | Entry point: build a well-formed mission from your arguments and invoke the `observe-run` agent |
| [`/odd-instrument`](.apm/prompts/odd-instrument.prompt.md) (prompt) | Entry point: point the `otel-instrumentation-expert` agent at a codebase |
| [`/odd-verify`](.apm/prompts/odd-verify.prompt.md) (prompt) | Entry point: replay a stored report's protocol through the `observe-run` agent — a full observation report again, this time ruling on everything the previous one recorded: measurements, anomalies, telemetry gaps |

The loop: **investigate** (agents) → **spec & implement** (the main
agent's spec-driven workflow) → **observe again** — telemetry on both
ends. Each observation report is stored in the observed repo
(`.odd/observe-run-reports/`), versioned by git and shared with the whole
team, and becomes the baseline the next run diffs against — the loop
accumulates knowledge instead of starting blind.

## Development

```bash
uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server
bash integration-tests/mcp-server/run.sh   # end-to-end via an MCP client; needs Docker
```

The project under `src/` is a self-contained uv project (own
`pyproject.toml`); `tests/` mirrors `src/`.

## License

[MIT](LICENSE)
