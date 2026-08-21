---
name: observe-local-run
description: Observe a locally running service through its telemetry - traces, metrics, and logs. Use when asked to look at what a local run is actually doing, inspect traces or spans, check request latency or error rates, read a service's logs, or explore the telemetry of a service. Input - the service name (its OTEL_SERVICE_NAME). Uses the oddyssey MCP tools and the Grafana datasource proxy.
---

# Observe a Local Run

You have MCP tools from the `oddyssey` server and a local Grafana stack to
look at what a running service actually does — traces, metrics, and logs —
instead of guessing from stdout.

Input: the **service name** (the `OTEL_SERVICE_NAME` the app was started
with). The app must be exporting OTLP to `http://localhost:4317`; see the
`measure-change-impact` skill for the zero-code instrumentation command.

## Workflow

1. **Stack.** Call `odd_stack_status`. If not running, call `odd_stack_up`
   (first run pulls the Docker image). Everything below goes through
   Grafana on :3000 — no other port is exposed.
2. **Overview first.** Call `odd_summarize(service=<service>,
   window_seconds=<covering the run>)` for the compact numbers: p95
   latency, request and error counts, DB operation count, heaviest spans.
3. **Drill down with the Grafana datasource proxy.** All queries are plain
   `curl` against `http://localhost:3000/api/datasources/proxy/uid/<uid>/...`
   (no credentials needed on the local stack). Compute the window as unix
   epoch seconds.

   **Traces (Tempo, uid `tempo`)** — find traces, then fetch one:

   ```bash
   # TraceQL search: all traces of the service in the window
   curl -s -G "http://localhost:3000/api/datasources/proxy/uid/tempo/api/search" \
     --data-urlencode 'q={resource.service.name="<service>"}' \
     --data-urlencode "start=<epoch>" --data-urlencode "end=<epoch>" \
     --data-urlencode "limit=20"

   # Narrow with TraceQL, e.g. only traces containing DB spans, or slow ones
   #   q={resource.service.name="<service>" && span.db.system != nil}
   #   q={resource.service.name="<service>" && duration > 100ms}

   # Full span tree of one trace
   curl -s "http://localhost:3000/api/datasources/proxy/uid/tempo/api/traces/<traceID>"
   ```

   **Metrics (Prometheus, uid `prometheus`)** — instant queries:

   ```bash
   # p95 latency of the service (seconds)
   curl -s -G "http://localhost:3000/api/datasources/proxy/uid/prometheus/api/v1/query" \
     --data-urlencode 'query=histogram_quantile(0.95, sum by (le) (http_server_request_duration_seconds_bucket{job="<service>"}))'

   # Request count by route and status code
   curl -s -G "http://localhost:3000/api/datasources/proxy/uid/prometheus/api/v1/query" \
     --data-urlencode 'query=sum by (http_route, http_response_status_code) (http_server_request_duration_seconds_count{job="<service>"})'

   # What metrics exist for this service
   curl -s -G "http://localhost:3000/api/datasources/proxy/uid/prometheus/api/v1/series" \
     --data-urlencode 'match[]={job="<service>"}'
   ```

   **Logs (Loki, uid `loki`)** — LogQL range queries (nanosecond epochs):

   ```bash
   curl -s -G "http://localhost:3000/api/datasources/proxy/uid/loki/loki/api/v1/query_range" \
     --data-urlencode 'query={service_name="<service>"}' \
     --data-urlencode "start=<epoch_ns>" --data-urlencode "end=<epoch_ns>"

   # Only errors:  query={service_name="<service>"} |= "error"
   ```

4. **Report what the telemetry shows** — request rates, latency
   distribution, error spans with their attributes, the SQL statements
   behind an endpoint — with numbers and trace IDs, not adjectives.

## Rules

- Wait ~10 s after a run for metrics to flush, and up to ~60 s for traces
  to become searchable; if a Tempo search looks stale, confirm against a
  full trace fetch (`/api/traces/<traceID>`).
- This skill observes; it does not compare. To measure a change
  (before/after + budget verdict), use the `measure-change-impact` skill.
- The Grafana UI at http://localhost:3000 is available for the human; your
  path is the proxy API.
- When the session is done, call `odd_stack_down` to stop the stack.
