---
name: gcx-local-stack
description: Configure gcx against the local oddyssey Grafana stack and query its four signals (metrics, traces, logs, profiles) without touching the user's own gcx contexts. Use when querying the local stack on http://localhost:3000, when configuring gcx locally, when a command needs the Tempo, Prometheus, Loki, or Pyroscope datasource UID, or when gcx is unavailable and the queries must go through plain curl.
---

# gcx on the local oddyssey stack

The local stack is a single otel-lgtm container: Grafana on `:3000` with
`admin`/`admin`, OTLP on `:4317` (gRPC) and `:4318` (HTTP), and four
datasources — Tempo, Prometheus, Loki, Pyroscope — behind the Grafana
datasource proxy. Bring it up with the oddyssey MCP tools (`odd_stack_status`,
`odd_stack_up`) before configuring anything here.

## Configure an isolated context

Never edit the user's own gcx configuration. Point `GCX_CONFIG` at a
**stable per-session path** — stable so the file is written once and reused,
isolated so the user's contexts stay untouched:

```bash
export GCX_CONFIG="${TMPDIR:-/tmp}/oddyssey/gcx-local.yaml"
mkdir -p "$(dirname "$GCX_CONFIG")"
cat > "$GCX_CONFIG" << 'EOF'
current-context: local
contexts:
  local:
    grafana:
      server: http://localhost:3000
      user: admin
      password: admin
      org-id: 1
    default-prometheus-datasource: prometheus
    default-loki-datasource: loki
EOF
gcx config check
```

The two `default-*-datasource` entries make the `-d` flag unnecessary for
most metric and log commands; Tempo and Pyroscope still take `-d tempo` /
`-d pyroscope` explicitly.

Each shell invocation starts fresh, so `export GCX_CONFIG=...` again in every
command block (or prefix the command with it) — the file itself persists, so
the write and `gcx config check` happen only once per session. Use the
`setup-gcx` skill only if gcx itself is missing or broken at machine level;
for this stack the block above is the whole setup.

## Datasources

| Signal | Backend | UID | Query with | Language |
| --- | --- | --- | --- | --- |
| Traces | Tempo | `tempo` | `gcx traces labels/query/get -d tempo` | TraceQL |
| Metrics | Prometheus | `prometheus` | `gcx metrics labels/series/metadata/query` | PromQL |
| Logs | Loki | `loki` | `gcx logs labels/series/query` | LogQL |
| Profiles | Pyroscope | `pyroscope` | `gcx profiles list-profile-types/labels/query -d pyroscope` | profile selector |

Discover before you query: `gcx metrics series` / `metadata`, `gcx traces
labels`, `gcx logs labels`, `gcx profiles list-profile-types`. Every service
names its own telemetry — never assume a metric, label, or stream exists.

## This stack is push-based

Apps push OTLP into the stack; Prometheus scrapes nothing here. So
`up{job="<service>"}` is **empty for every service, healthy or not** — it
proves nothing, and any workflow that gates on it (including the
`debug-with-grafana` liveness step) must skip it. Prove a service is present
with its own data instead: a Tempo search for
`{resource.service.name="<svc>"}`, a Prometheus series carrying it
(`target_info{service_name="<svc>"}` or whatever discovery returns), a Loki
stream selecting it.

Also absent from this stack: `gcx assistant` and investigations — Grafana
Cloud features the local anonymous instance does not serve.

## curl fallback

If gcx cannot be installed or configured, the same queries go over plain
HTTP through the datasource proxy —
`http://localhost:3000/api/datasources/proxy/uid/<uid>/...`, basic auth
`admin:admin`:

```bash
# Metrics (Prometheus API under the proxy)
curl -s -u admin:admin --get \
  'http://localhost:3000/api/datasources/proxy/uid/prometheus/api/v1/query' \
  --data-urlencode 'query=sum by (job) (target_info)'

# Traces (Tempo search, then the full trace)
curl -s -u admin:admin --get \
  'http://localhost:3000/api/datasources/proxy/uid/tempo/api/search' \
  --data-urlencode 'q={resource.service.name="<svc>"}'
curl -s -u admin:admin \
  'http://localhost:3000/api/datasources/proxy/uid/tempo/api/traces/<trace-id>'

# Logs (Loki range query)
curl -s -u admin:admin --get \
  'http://localhost:3000/api/datasources/proxy/uid/loki/loki/api/v1/query_range' \
  --data-urlencode 'query={service_name="<svc>"}' --data-urlencode 'limit=50'

# Profiles (Pyroscope render; confirm the path against the datasource first,
# it is the least stable of the four)
curl -s -u admin:admin --get \
  'http://localhost:3000/api/datasources/proxy/uid/pyroscope/pyroscope/render' \
  --data-urlencode 'query=process_cpu:cpu:nanoseconds:cpu:nanoseconds{service_name="<svc>"}' \
  --data-urlencode 'from=now-30m'
```

The proxy path shape is the same on any Grafana, so a query written here
also runs against a remote stack once the UIDs are swapped.
