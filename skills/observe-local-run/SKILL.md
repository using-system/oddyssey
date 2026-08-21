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
   window_seconds=<covering the run>)` for a quick HTTP-centric summary.
   It only covers standard HTTP/DB signals — the app's own telemetry
   (custom metrics, domain spans, log fields) is what the drill-down
   below is for.
3. **Drill down with the Grafana datasource proxy.** Every service emits
   its own metrics, spans, and logs, so NEVER assume names: **discover
   first, then query what you found**. All calls are plain `curl` against
   `http://localhost:3000/api/datasources/proxy/uid/<uid>/...` (no
   credentials on the local stack). Windows are unix epoch seconds
   (nanoseconds for Loki).

   **Traces (Tempo, uid `tempo`)** — discover the attributes, search, fetch:

   ```bash
   BASE=http://localhost:3000/api/datasources/proxy/uid/tempo

   # What attribute names exist on this service's spans?
   curl -s -G "$BASE/api/v2/search/tags" --data-urlencode 'scope=span'
   # What values does one attribute take?
   curl -s "$BASE/api/v2/search/tag/span.<attribute>/values"

   # Search traces with TraceQL — start from the service, then narrow with
   # whatever attributes/durations the discovery showed:
   curl -s -G "$BASE/api/search" \
     --data-urlencode 'q={resource.service.name="<service>"}' \
     --data-urlencode "start=<epoch>" --data-urlencode "end=<epoch>" \
     --data-urlencode "limit=20"
   #   ... && span.<attribute> = "<value>"     attribute filter
   #   ... && duration > 100ms                 slow traces
   #   ... && status = error                   failed spans

   # Full span tree of one trace (all spans, attributes, events):
   curl -s "$BASE/api/traces/<traceID>"
   ```

   **Metrics (Prometheus, uid `prometheus`)** — discover the series, then
   query them:

   ```bash
   BASE=http://localhost:3000/api/datasources/proxy/uid/prometheus

   # Which metrics does this service export? (job = OTEL_SERVICE_NAME)
   curl -s -G "$BASE/api/v1/series" --data-urlencode 'match[]={job="<service>"}'
   # Which labels does one metric carry?
   curl -s -G "$BASE/api/v1/series" --data-urlencode 'match[]=<metric_name>{job="<service>"}'

   # Then query the metrics you discovered — instant value or over time:
   curl -s -G "$BASE/api/v1/query" \
     --data-urlencode 'query=<any PromQL over the discovered metrics>'
   curl -s -G "$BASE/api/v1/query_range" \
     --data-urlencode 'query=<PromQL>' \
     --data-urlencode "start=<epoch>" --data-urlencode "end=<epoch>" \
     --data-urlencode "step=15"
   # Histograms come as <name>_bucket/_sum/_count series; quantiles via
   # histogram_quantile(0.95, sum by (le) (<name>_bucket{job="<service>"})).
   ```

   **Logs (Loki, uid `loki`)** — discover the streams, then query:

   ```bash
   BASE=http://localhost:3000/api/datasources/proxy/uid/loki

   # Which labels/streams exist? (OTel logs carry service_name)
   curl -s "$BASE/loki/api/v1/labels"
   curl -s "$BASE/loki/api/v1/label/<label>/values"

   # Then LogQL over the discovered streams:
   curl -s -G "$BASE/loki/api/v1/query_range" \
     --data-urlencode 'query={service_name="<service>"}' \
     --data-urlencode "start=<epoch_ns>" --data-urlencode "end=<epoch_ns>"
   # Narrow with the app's own log content: |= "text", | json | <field>=...
   ```

4. **Report what the telemetry shows**, in the app's own vocabulary — the
   spans, metric names, and log fields you actually discovered — with
   numbers and trace IDs, not adjectives.

## Rules

- Wait ~10 s after a run for metrics to flush, and up to ~60 s for traces
  to become searchable; if a Tempo search looks stale, confirm against a
  full trace fetch (`/api/traces/<traceID>`).
- This skill observes; it does not compare. To measure a change
  (before/after + budget verdict), use the `measure-change-impact` skill.
- The Grafana UI at http://localhost:3000 is available for the human; your
  path is the proxy API.
- When the session is done, call `odd_stack_down` to stop the stack.
