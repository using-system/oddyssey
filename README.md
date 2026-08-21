# oddyssey

**Observability-Driven Development (ODD) for CLI coding agents.**

## The idea

Spec-Driven Development gets an agent to write the right code. ODD is the
step after: the agent **proves** the code with observability. It runs the
service, reads the telemetry — latency, error rates, DB query counts — and
refuses regressions, instead of trusting stdout and exit codes. An N+1
query is invisible in logs and unmissable in a trace.

This repo is that loop, packaged for any coding agent
([APM](https://microsoft.github.io/apm/): Claude Code, Copilot, Cursor,
Codex, Gemini, and friends).

## The MCP server

Its job: **pilot a local Grafana stack with an OpenTelemetry endpoint**.
One container ([grafana/otel-lgtm](https://github.com/grafana/docker-otel-lgtm),
pinned) exposes Grafana on `:3000` and OTLP on `:4317`/`:4318`; the app
under test exports its telemetry there with zero code changes
(`opentelemetry-instrument`). All queries — Tempo traces, Prometheus
metrics, Loki logs — go through the Grafana datasource proxy
(`:3000/api/datasources/proxy/uid/...`), so the same paths work against any
Grafana; on remote environments the stack behind it can be something other
than the local otel-lgtm container.

Six tools:

| Tool | What it does |
| --- | --- |
| `odd_stack_up` / `odd_stack_down` / `odd_stack_status` | Start, stop, probe the local stack |
| `odd_summarize` | One compact report for a service over a time window: p95, requests, errors, DB spans, heaviest spans |
| `odd_baseline` | Measure and store the reference report (`.odd/baseline.json`) |
| `odd_diff` | Measure again, pair every metric `before → after`, verdict against `.odd/perf-budget.yml` (`max` / `max_increase` rules → `pass` / `fail` / `no_budget`) |

## The skills and agents

| Primitive | Role |
| --- | --- |
| [`measure-change-impact`](skills/measure-change-impact/SKILL.md) (skill) | Measure what a code change really did: baseline before, diff after, iterate until the budget passes |
| [`observe-local-run`](agents/observe-local-run.agent.md) (agent) | Observe a running service (metrics, traces, logs, profiles via the [gcx](https://github.com/grafana/gcx) skills) and hand back every input needed to build a spec-driven plan of fixes and improvements |

The loop: **observe** (agent) → **spec & implement** (the main agent's
spec-driven workflow) → **measure** (skill) — telemetry on both ends.

## Install

```bash
apm install using-system/oddyssey
```

Or wire the server into any `mcpServers` config:

```json
{
  "mcpServers": {
    "oddyssey": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/using-system/oddyssey#subdirectory=src/mcp-server",
        "oddyssey-mcp"
      ]
    }
  }
}
```

From a clone, run it from the working tree instead:
`uv run --project src/mcp-server oddyssey-mcp`.

## The proof

`examples/n-plus-one` is a FastAPI demo whose `GET /users` runs one query
per user; `ODD_FIXED=1` switches to a single joined query. Measured on 200
identical requests ([spike notes](docs/superpowers/spike-notes-2026-08-17.md),
[live e2e run](docs/superpowers/e2e-notes-2026-08-17.md)):

| Metric | N+1 | Fixed |
| --- | --- | --- |
| p95 latency | 22.8 ms | 4.9 ms |
| DB spans per run | 10400 | 400 |
| SQL visible in stdout | 0 | 0 |

The app's own output is byte-identical in both variants — only the
telemetry sees the difference. `odd_diff` returns it as `before → after`
per metric with `verdict: "pass"`.

## Development

```bash
uv run --project src/summarize pytest -c src/summarize/pyproject.toml tests/summarize
uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server
uv run --project src/summarize pytest -c src/summarize/pyproject.toml tests/summarize -m integration -o addopts=""  # needs the live stack
```

Each project under `src/` is a self-contained uv project (own
`pyproject.toml`); `tests/` mirrors `src/`. The full manual walkthrough
(instrument, load, baseline, diff) is in the
[e2e notes](docs/superpowers/e2e-notes-2026-08-17.md).

## License

[MIT](LICENSE)
