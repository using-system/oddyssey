# Spike measurements — 2026-08-17

Scenario: 200 sequential GET /users, 50 users x 5 posts, SQLite, single uvicorn worker.

Stack: `grafana/otel-lgtm:0.30.2` (`docker-compose/docker-compose.yml`), Prometheus API on
`:9090`, Tempo API on `:3200`, OTLP gRPC on `:4317`. App instrumented with
`opentelemetry-instrument` (`opentelemetry-distro==0.65b0`) and
`OTEL_SEMCONV_STABILITY_OPT_IN=http`, `OTEL_METRIC_EXPORT_INTERVAL=5000`.

## Verified names

| Concept | Verified value |
| --- | --- |
| Prometheus duration histogram | `http_server_request_duration_seconds` (series: `_bucket` / `_count` / `_sum`) |
| Service selector label | `job="n-plus-one"` (mirrored by `service_name="n-plus-one"`) |
| Status code label | `http_response_status_code` (string, e.g. `"200"`) |
| Tempo DB attribute (TraceQL) | `span.db.system` (value `sqlite`) — `span.db.system.name` returns nothing |

How they were confirmed:

- `GET /api/v1/label/__name__/values` lists exactly
  `http_server_active_requests`, `http_server_request_duration_seconds_{bucket,count,sum}`,
  `http_server_response_body_size_bytes_{bucket,count,sum}`, `db_client_connections_usage`.
  There is no `http_server_duration_milliseconds` (old semconv) — the stable HTTP semconv opt-in
  is in effect.
- `GET /api/v1/query?query=http_server_request_duration_seconds_count` returns series labelled:
  `http_request_method="GET"`, `http_response_status_code="200"`, `http_route="/users"`,
  `instance`, `job="n-plus-one"`, `network_protocol_version="1.1"`, `service_instance_id`,
  `service_name="n-plus-one"`, `url_scheme="http"`.
  There is no `status_code` / `http_status_code` label.
- TraceQL `{resource.service.name="n-plus-one" && span.db.system != nil}` returns matching
  span sets (`db.system` = `sqlite`); the same query with `span.db.system.name` returns
  `{"traces": []}`.
- Other useful Tempo response fields: `traces[].spanSet.matched` (count of matching spans in the
  trace) and `traces[].serviceStats["n-plus-one"].spanCount` (total spans in the trace).

## Measurements

Measurement windows (epoch seconds, one shared stack lifetime):
N+1 `[1786959925, 1786959939]`, fixed `[1786959977, 1786959990]`.
The two runs are separate uvicorn processes, so their counters are distinct series; each run was
pinned with `OTEL_RESOURCE_ATTRIBUTES=service.instance.id=BASELINE|FIXED` to make the
`instance` label deterministic instead of a random UUID.

| Metric | N+1 (default) | Fixed (ODD_FIXED=1) |
| --- | --- | --- |
| p95 latency | 0.02275 s (22.8 ms) | 0.00495 s (4.9 ms) |
| HTTP requests | 200 | 200 |
| DB spans | 10400 (52 per request) | 400 (2 per request) |

Supporting numbers:

| Metric | N+1 (default) | Fixed (ODD_FIXED=1) |
| --- | --- | --- |
| p50 latency | 0.00860 s | 0.00260 s |
| total request time (histogram `_sum`) | 2.2898 s | 0.5816 s |
| traces in window (`{resource.service.name="n-plus-one"}`) | 201 | 201 |
| per-trace `db.system` spans | 52 | 2 |
| app stdout lines | 209 | 209 |
| SQL statements visible in app stdout | 0 | 0 |

Per-trace span breakdown, from `GET /api/traces/<id>` on one trace of each run:

- N+1: 55 spans — `GET /users` (1), `GET /users http send` (2), `connect` (1),
  `SELECT ./demo.db` (51 = 1 users query + 50 per-user posts queries). 52 carry `db.system`.
- Fixed: 5 spans — `GET /users` (1), `GET /users http send` (2), `connect` (1),
  `SELECT ./demo.db` (1). 2 carry `db.system`.

The 201st trace in each window is the readiness probe (`GET /__odd_probe`, HTTP 404); it issues no
queries, so it never matches the `db.system` search. The `/users` request counts above are scoped
with `http_route="/users"` and therefore exclude it.

### PromQL / TraceQL actually used

```promql
# p95 latency (seconds), per run
histogram_quantile(0.95, sum by (le) (
  http_server_request_duration_seconds_bucket{job="n-plus-one", instance="BASELINE", http_route="/users"}))

# request count, per run
sum(http_server_request_duration_seconds_count{job="n-plus-one", instance="BASELINE", http_route="/users"})
```

```
# DB spans, per run (sum of spanSet.matched over the run's window; N+1 window shown)
GET :3200/api/search
    ?q={resource.service.name="n-plus-one" && span.db.system != nil}
    &start=1786959925&end=1786959939&limit=1000
```

### Deviations from the planned queries, and why

1. **`increase()` over the load window returns `0` / `NaN` here.** The 200 requests complete in
   ~2 s while metrics are exported every 5 s, so the counter's *first* sample already holds the
   final value (200) and stays flat. Prometheus cannot extrapolate a pre-window value for a series
   that starts inside the window, so
   `sum(increase(http_server_request_duration_seconds_count{...}[14s]))` evaluates to `0` and the
   `histogram_quantile(...increase(...))` form to `NaN`. Both were observed for both runs.
   Because each variant runs in a fresh process, the *cumulative* counter for that process is
   already the per-run delta, so the queries above read the raw cumulative series instead. A
   consumer that must use rate/increase needs either a longer load phase (>= 3-4 export intervals)
   or per-`instance` cumulative reads as done here.
2. **Readiness probe moved off `/users`.** Polling `/users` to detect startup added a 201st request
   to the measured series. The probe now hits an unrouted path (`/__odd_probe`, 404), which lands
   in its own series with no `http_route` label, keeping the measured `/users` count at exactly 200.

### Timing caveat (flakiness)

Querying Tempo immediately after a run gave a wrong answer: the fixed-variant search returned
`matched=52` per trace with byte-for-byte the same `inspectedBytes` (330254) as the preceding
N+1 query — a stale/cached block response. Re-running the same query ~60 s later returned the
correct `matched=2` (`inspectedBytes` 84597), which a full `GET /api/traces/<id>` fetch confirms
(5 spans, 2 with `db.system`). Anything automating this must allow Tempo time to make the run
searchable and should sanity-check the per-trace count against a full trace fetch rather than
trusting the first search response.

## Conclusion

The N+1 is completely invisible in the application's own output: both variants print the same log
shape — 209 stdout lines each (4 startup, 1 probe, 200 x `"GET /users HTTP/1.1" 200 OK`,
4 shutdown) with zero SQL statements — so nothing distinguishes a request that ran 1 query from one
that ran 51. In the trace data the difference is unmissable:
52 `db.system` spans per request versus 2, i.e. 10400 versus 400 DB spans for the same 200 requests,
with p95 latency 22.8 ms versus 4.9 ms (4.6x). This is the go/no-go evidence: the OTel signals
already contain everything needed to name the defect, so a summarizer reading Prometheus and Tempo
over a fixed window can surface an N+1 that logs and eyeballing never would.
