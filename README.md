# oddyssey

**Observability-driven development for CLI coding agents.**

AI coding agents write code they can't verify. They see stdout and exit
codes — not latency, not error rates, not the N+1 query they just
introduced.

oddyssey closes the loop. It spins up a local OpenTelemetry backend,
instruments your app, replays a scenario, and hands the agent a compact
report it can diff against the previous run: p95 latency, error rate,
query count, top spans. Define a budget, and the agent iterates until
the numbers pass.

No dashboards to read. No cloud account. Just a verdict.

## The idea in 30 seconds

This repo ships a demo FastAPI app with a deliberate N+1 query. In
stdout, both variants look identical: 200 requests, 200 × HTTP 200.
In the telemetry, they don't (numbers measured on this repo's demo,
200 sequential requests, 50 users × 5 posts, SQLite):

| Metric | N+1 (default) | Fixed (`ODD_FIXED=1`) |
| --- | --- | --- |
| p95 latency | 22.8 ms | 4.9 ms |
| DB spans per run | 10400 | 400 |

Same output, 78% lower p95 and 96% fewer DB spans.

The target UX (roadmap — the diff/verdict engine is step 3):

```text
$ odd baseline
✓ 200 requests · p95 0.0228s · 1 endpoint · 10400 db spans

# ... the agent edits the code ...

$ odd diff
✓ p95            0.0228s → 0.0049s
✓ db spans       10400 → 400
✗ errors         0 → 2    NEW: TimeoutError in /users
verdict: FAIL (perf-budget: errors must not increase)
```

## Quickstart

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/).

```bash
# 1. Start the local observability backend (Grafana on :3000)
docker compose -f docker-compose/docker-compose.yml up -d

# 2. Seed and run the instrumented demo app
cd examples/n-plus-one
uv run python -m app.seed
env OTEL_SERVICE_NAME=n-plus-one \
    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
    OTEL_SEMCONV_STABILITY_OPT_IN=http \
    OTEL_METRIC_EXPORT_INTERVAL=5000 \
    uv run opentelemetry-instrument uvicorn app.main:app --port 8000

# 3. In another terminal: replay the load scenario
cd examples/n-plus-one && uv run python -m app.load

# 4. Summarize the run
cd ../.. && uv run python -c "
import json, time
from oddyssey.summarize.app.report import summarize
end = int(time.time())
print(json.dumps(summarize('n-plus-one', end - 900, end), indent=2))
"
```

Pass a window that covers only the run you care about: the report counts
every request the service handled inside it, so a warm-up request — or a
previous variant's run — lands in the numbers too. And give Tempo a
minute after the load finishes; a search issued immediately can come back
with a stale span count.

Fix the N+1 by restarting the app with `ODD_FIXED=1`, rerun the load,
and compare the reports.

## What exists today

- `examples/n-plus-one` — reproducible demo app; both variants live in
  the same file, toggled by `ODD_FIXED=1`.
- `src/oddyssey/` — the summarizer: queries Tempo and Prometheus over a time
  window and emits a compact JSON report keyed by OpenTelemetry semantic
  conventions.
- `.odd/perf-budget.yml` — the budget format (not enforced yet).

## Roadmap

1. ~~Prove the loop on a real N+1~~ (done — numbers above)
2. ~~Summarizer: raw telemetry → compact report~~ (done)
3. Baseline storage, `diff`, budget verdict, non-zero exit code
4. MCP server + thin per-CLI shells, auto-instrumentation of user
   projects, APM (Agent Package Manager) manifest

## Under the hood

The backend is the [grafana/otel-lgtm](https://github.com/grafana/docker-otel-lgtm)
image (pinned): OpenTelemetry Collector, Tempo (traces), Prometheus
(metrics), Loki (logs), Grafana. The demo app is instrumented with
zero code changes via `opentelemetry-instrument`. The summarizer talks
to the Tempo and Prometheus HTTP APIs on :3200 and :9090.

## Development

```bash
uv run pytest tests/            # unit tests (no Docker needed)
uv run pytest tests/ -m integration -o addopts=""   # needs the stack + a fresh run
```

## License

[MIT](LICENSE)
