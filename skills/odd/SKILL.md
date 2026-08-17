---
name: odd
description: Observability-Driven Development loop for local runs. Use when asked to measure the performance impact of a change, hunt a regression or an N+1 query, verify an optimization actually worked, or set up local observability (traces/metrics) for a dev run. Uses the oddyssey MCP tools (odd_stack_up, odd_summarize, odd_baseline, odd_diff).
---

# Observability-Driven Development

You have MCP tools from the `oddyssey` server to measure what code changes
actually do to a running service — latency, error counts, DB query volume —
instead of trusting stdout.

## The loop

1. **Stack.** Call `odd_stack_status`. If not running, call `odd_stack_up`
   (first run pulls the Docker image; it can take a couple of minutes). The
   stack exposes Grafana on :3000 and an OTLP endpoint on :4317.
2. **Instrument the app under test** (zero code changes). Run it with:

   ```bash
   env OTEL_SERVICE_NAME=<service> \
       OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
       OTEL_SEMCONV_STABILITY_OPT_IN=http \
       OTEL_METRIC_EXPORT_INTERVAL=5000 \
       opentelemetry-instrument <the usual run command>
   ```

   Python apps need `opentelemetry-distro`, `opentelemetry-exporter-otlp`,
   and the instrumentation packages for their frameworks installed.
3. **Replay a deterministic scenario** against the running app (a fixed
   number of identical requests). The same scenario must be replayed for
   every measurement — no scenario, no signal.
4. **Baseline before changing code.** After the scenario, wait ~10 s for
   metrics to flush and ~60 s for traces to become searchable, then call
   `odd_baseline(service=<service>, window_seconds=<covering the run>)`.
5. **Change the code**, restart the app (ALWAYS a fresh process per
   measured run — the metrics depend on it), replay the same scenario, wait
   the same delays, then call `odd_diff(service=..., window_seconds=...)`.
6. **Read the verdict.** `fail` lists the violated budget rules
   (`.odd/perf-budget.yml` in the project, `max` and `max_increase` rules);
   iterate on the code and re-run step 5 until it passes. `no_budget` means
   no budget file exists — report the delta and suggest adding one.

## Rules

- Never trust stdout over the report: an N+1 query is invisible in logs and
  obvious in `db.client.operation.count` and `top_spans`.
- One fresh app process per measured run; identical scenario every time.
- Pick `window_seconds` to cover the current run only — overlapping windows
  blend runs of the same service.
- Report the numbers from the diff (before → after), not adjectives.
