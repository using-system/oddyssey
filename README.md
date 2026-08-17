# oddyssey

**Observability-Driven Development for CLI coding agents.**

AI coding agents write code they can't verify. They see stdout and exit
codes — not latency, not error rates, not the N+1 query they just
introduced. oddyssey is an [APM](https://microsoft.github.io/apm/) package
that gives any coding agent eyes: a local OpenTelemetry backend, an MCP
server with measurement tools, and a skill that teaches the agent to
measure before/after every change and refuse regressions.

## Install

```bash
apm install using-system/oddyssey
```

One manifest, every harness APM supports (Claude Code, Copilot, Cursor,
Codex, Gemini, OpenCode, Windsurf, Kiro, Grok Build). The agent gets:

- the **`odd` skill** — the ODD loop: stack up → instrument → replay a
  scenario → baseline → change code → diff → iterate until the budget passes;
- the **`oddyssey` MCP server** — six tools: `odd_stack_up`,
  `odd_stack_down`, `odd_stack_status`, `odd_summarize`, `odd_baseline`,
  `odd_diff`.

The manifest fetches the server straight from this repository's default
branch (`uvx --from git+https://github.com/using-system/oddyssey…`), so the
one-line install becomes functional once this work lands on `main`. Until
then — and for hacking on oddyssey itself — use the manual path below.

## Proof: an N+1 the logs cannot see

`examples/n-plus-one` is a FastAPI app whose `GET /users` lazily loads each
user's posts one query at a time. `ODD_FIXED=1` switches the same endpoint to
a single joined query. Nothing else changes.

Measured on this repo's demo: 200 sequential `GET /users`, 50 users × 5
posts, SQLite, one fresh uvicorn process per run
([spike notes](docs/superpowers/spike-notes-2026-08-17.md)).

| Metric | N+1 (default) | Fixed (`ODD_FIXED=1`) |
| --- | --- | --- |
| p95 latency | 22.8 ms | 4.9 ms |
| DB spans per run | 10400 (52/request) | 400 (2/request) |
| HTTP requests | 200 | 200 |
| App stdout lines | 209 | 209 |
| SQL statements in stdout | 0 | 0 |

That is the whole problem in one table. The application's own output is
identical — 209 lines, 200 × `"GET /users HTTP/1.1" 200 OK`, zero SQL — so
nothing an agent can read tells it whether a request ran 1 query or 51. The
telemetry says it immediately: 26× fewer DB spans, p95 down 78%.

Here is `odd_diff` naming it, excerpted from a real live run against the
stack ([e2e notes](docs/superpowers/e2e-notes-2026-08-17.md) — baseline taken
on the N+1 variant, diff on the fixed one, with `.odd/perf-budget.yml` in
place):

```json
{
  "delta": {
    "http.server.request.duration.p95": { "before": 0.0198, "after": 0.0049, "unit": "s" },
    "http.server.request.count": { "before": 201, "after": 201 },
    "http.server.error.count": { "before": 0, "after": 0 },
    "db.client.operation.count": { "before": 10400, "after": 400 }
  },
  "verdict": "pass",
  "violations": []
}
```

No dashboards to read, no cloud account: an agent gets `before → after` per
metric and a verdict it can act on. Two details worth knowing:

- `http.server.request.count` is 201, not 200. The summarizer counts every
  request the service handled in the window, and the run protocol fires one
  readiness probe (`GET /__odd_probe`, 404) before the 200-request scenario.
  It is identical on both sides, so it cancels out of the delta.
- p95 is a per-run measurement, not a constant. The same comparison in the
  spike read 22.8 ms → 4.9 ms and here 19.8 ms → 4.9 ms; the ratio and the
  DB span counts (10400 → 400) reproduce exactly.

## What's in the box

```text
apm.yml                       the APM manifest — package identity + the MCP dependency
skills/odd/SKILL.md           the ODD loop, written for the agent
src/summarize/                the summarizer: Tempo + Prometheus → one compact JSON report
src/mcp-server/               the MCP server: stack lifecycle, baseline store, diff, budget
tests/summarize/              unit tests + fixtures + a live-stack integration test
tests/mcp-server/             unit tests (no Docker)
docker-compose/               grafana/otel-lgtm:0.30.2, pinned
examples/n-plus-one/          the demo app; both variants in one file
.odd/perf-budget.yml          the budget the verdict is computed against
```

The backend is the [grafana/otel-lgtm](https://github.com/grafana/docker-otel-lgtm)
image: OpenTelemetry Collector, Tempo (traces), Prometheus (metrics), Loki
(logs), Grafana. One container, five ports — Grafana on `:3000`, OTLP on
`:4317`/`:4318`, Tempo on `:3200`, Prometheus on `:9090`. Apps are
instrumented with zero code changes via `opentelemetry-instrument`; the
summarizer reads the Tempo and Prometheus HTTP APIs over a fixed time window
and emits one report keyed by OpenTelemetry semantic conventions:
`http.server.request.duration.p95`, `http.server.request.count`,
`http.server.error.count`, `db.client.operation.count`, plus the five
heaviest spans by total duration.

`odd_baseline` stores such a report as `.odd/baseline.json` (override the
directory with `ODD_DIR`); `odd_diff` measures again, pairs each metric
`before → after`, and evaluates the budget:

```yaml
# .odd/perf-budget.yml
odd_version: "1"
service: n-plus-one
budget:
  http.server.request.duration.p95:
    max: 0.150            # seconds — current value must not exceed this
  http.server.error.count:
    max_increase: 0       # errors must not increase vs baseline
  db.client.operation.count:
    max_increase: 0       # DB query count must not grow vs baseline
```

Two rule kinds: `max` (an absolute ceiling on the current run) and
`max_increase` (how much the metric may grow relative to the baseline). The
verdict is `pass`, `fail` (with a `violations` list naming metric, rule,
limit, baseline and current), or `no_budget` when no budget file exists.

## Try it without APM

Prerequisites: Docker and [uv](https://docs.astral.sh/uv/). This is the
sequence validated live in the e2e notes, run from the repo root unless noted;
there, steps 1 and 7 were driven through `odd_stack_up`/`odd_stack_down`, which
run the same compose file.

```bash
# 1. Start the stack (this is what odd_stack_up does; the first run pulls the image)
docker compose -f docker-compose/docker-compose.yml up -d

# 2. Seed the database and run the instrumented demo app (leave it running)
cd examples/n-plus-one
uv run python -m app.seed
env OTEL_SERVICE_NAME=n-plus-one \
    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
    OTEL_SEMCONV_STABILITY_OPT_IN=http \
    OTEL_METRIC_EXPORT_INTERVAL=5000 \
    uv run opentelemetry-instrument uvicorn app.main:app --port 8000

# 3. In another terminal: wait for readiness, then replay the scenario
cd examples/n-plus-one
until [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/__odd_probe)" = "404" ]; do sleep 0.5; done
uv run python -m app.load          # -> done: 200 requests, 0 errors

# 4. Back in the repo root: wait ~75 s (~10 s metric flush, ~60 s Tempo
#    searchability), then take the baseline. It is written to .odd/baseline.json;
#    export ODD_DIR=/some/scratch/odd first to keep it out of the repo.
uv run --project src/mcp-server python -c "
from oddyssey_mcp.server import odd_baseline
import json
print(json.dumps(odd_baseline('n-plus-one', 300), indent=2))"

# 5. Stop the app, restart it with ODD_FIXED=1 (a fresh process per measured
#    run is mandatory), replay the same load, wait the same ~75 s.

# 6. Diff: size window_seconds so the window covers the fixed run and nothing
#    else. The budget is read from the same directory as the baseline
#    ($ODD_DIR/perf-budget.yml, default .odd/perf-budget.yml; ODD_BUDGET_FILE
#    overrides the path). No budget file means verdict "no_budget".
uv run --project src/mcp-server python -c "
from oddyssey_mcp.server import odd_diff
import json
print(json.dumps(odd_diff('n-plus-one', 120), indent=2))"

# 7. Tear down (this is what odd_stack_down does)
docker compose -f docker-compose/docker-compose.yml down
```

The window is the whole trick: `window_seconds` counts back from now, and the
report includes everything the service did inside it — a warm-up request or
the previous variant's run lands in the numbers too. Overlap the two runs and
the diff is meaningless.

To wire the MCP server into a client that reads the standard
`mcpServers` config (Claude Code, Cursor, and friends) instead of installing
through APM:

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

Same caveat as `apm install`: the git URL resolves to the default branch, so
it works once this lands on `main`. From a clone of this repo, run the server
from the working tree instead — `uv run --project src/mcp-server oddyssey-mcp`
(stdio transport, no arguments).

## Development

```bash
uv run --project src/summarize pytest -c src/summarize/pyproject.toml tests/summarize      # summarizer unit tests
uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server    # server unit tests
uv run --project src/summarize pytest -c src/summarize/pyproject.toml tests/summarize -m integration -o addopts=""  # needs the stack + a fresh run
```

Each project under `src/` is a self-contained uv project with its own
`pyproject.toml` and pytest configuration; there is no root `pyproject.toml`.
The integration test is deselected by default and only passes against a live
stack that has just seen a load run.

## Roadmap

- **Auto-instrumentation of user projects** — the skill currently hands the
  agent the `OTEL_*` env block; detecting the runtime and wiring it should be
  the server's job.
- **Probe and route filtering** — let the caller scope a measurement to a
  route (`http_route="/users"`) so readiness probes stay out of the counts.
- **MCP registry publication** — a versioned release instead of `uvx --from
  git+…` against a branch.
- **CI budget gate** — the same verdict as a pull-request check, with a
  non-zero exit code when the budget fails.

## License

[MIT](LICENSE)
