---
name: setup-local-stack
description: Configure gcx against the local oddyssey Grafana stack and query its four signals (metrics, traces, logs, profiles) without touching the user's own gcx contexts. Owns the global configuration's "local" stack value. Use when the configured stack is "local", when querying the local stack (Grafana host port from the global configuration, default 3000), when configuring gcx locally, when a command needs the Tempo, Prometheus, Loki, or Pyroscope datasource UID. gcx is the mandatory query CLI for the stack - install it if missing (brew install gcx, or the official install script from github.com/grafana/gcx).
---

# gcx on the local oddyssey stack

The local stack is a single otel-lgtm container: Grafana, OTLP (gRPC and
HTTP), and four datasources — Tempo, Prometheus, Loki, Pyroscope — behind
the Grafana datasource proxy. The host ports come from the **global
configuration** (defaults `3000` / `4317` / `4318`): read the effective
URLs from `odd_stack_up`'s result (`grafana_url`, `otlp_endpoint`) or
`odd_config_get` — never assume the defaults, and point an application's
`OTEL_EXPORTER_OTLP_ENDPOINT` at those values, never at a hardcoded
port. Grafana serves its API **anonymously** here: no credentials are
required, and the
`admin`/`admin` entries in the context below are accepted but inert (kept
only so the template also fits an auth-enabled Grafana).

The stack holds no volume **by design** — a reset wipes everything, and
the observation report is the only durable artifact. To configure the
container, pass `env` to `odd_stack_up`/`odd_stack_reset`; env (like the
embedded defaults, e.g. delta-metric ingestion) applies at container
creation only, so a container predating the current oddyssey version
keeps its old definition until its next reset. An applied env is
persisted into the global configuration's `stack_config.local` and
reapplied on every later recreation, so it survives resets without being
repeated — except credential-named variables (headers, tokens, ...),
which are applied but never persisted (the result's `env_not_persisted`
names them): pass those again on every recreation. The catalog of the
image's variables — per-component debug logs, backend tuning, OTLP
forwarding to a remote backend, OBI, `GF_*` — is
[`references/otel-lgtm-env.md`](references/otel-lgtm-env.md), aligned on
the pinned image tag. For anything env cannot
express (volumes, networks), the supported escape hatch is a manual
`docker run` reusing the same name and ports — `status`/`up`/`down` keep
working against it, but a **reset recreates the container from the
embedded definition plus env**: hand-mounted volumes and networks do not
survive it. Bring it up with the oddyssey MCP tools (`odd_stack_status`,
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
      server: http://localhost:3000   # odd_stack_up's grafana_url - default shown
      user: admin
      password: admin
      org-id: 1
    default-prometheus-datasource: prometheus
    default-loki-datasource: loki
    default-tempo-datasource: tempo
    default-pyroscope-datasource: pyroscope
EOF
gcx config check
```

The four `default-*-datasource` entries make the `-d` flag unnecessary; the
commands below keep it for explicitness, but it can be dropped.

Each shell invocation starts fresh, so `export GCX_CONFIG=...` again in every
command block (or prefix the command with it) — the file itself persists, so
the write and `gcx config check` happen only once per session. If gcx
itself is missing, install it (`brew install gcx`, or the official install
script from https://github.com/grafana/gcx); for this stack the block above is
the whole setup.

## Datasources

| Signal | Backend | UID | Query with | Language |
| --- | --- | --- | --- | --- |
| Traces | Tempo | `tempo` | `gcx traces labels/query/get -d tempo` | TraceQL |
| Metrics | Prometheus | `prometheus` | `gcx metrics labels/series/metadata/query` | PromQL |
| Logs | Loki | `loki` | `gcx logs labels/series/query` | LogQL |
| Profiles | Pyroscope | `pyroscope` | `gcx profiles list-profile-types/labels/query -d pyroscope` | profile selector |

This table is verified against gcx v1.0.0 and Grafana 13.1.3; the gcx
command surface moves between versions, so when a documented command
errors, trust `gcx <group> --help` over this table.

Discover before you query: `gcx metrics labels` / `gcx metrics metadata`,
`gcx traces labels`, `gcx logs labels`, `gcx profiles list-profile-types`.
`gcx metrics series` and `gcx logs series` are NOT discovery commands:
bare, they error — both require at least one selector (e.g. `gcx metrics
series 'target_info'`). Every service names its own telemetry — never
assume a metric, label, or stream exists.

## This stack is push-based

Apps push OTLP into the stack; Prometheus scrapes nothing here. So
`up{job="<service>"}` is **empty for every service, healthy or not** — it
proves nothing, and any workflow that gates on a scrape-style liveness
check must skip it. Prove a service is present with its own data instead: a
Tempo search for `{resource.service.name="<svc>"}`, a Prometheus series
carrying it (`target_info{service_name="<svc>"}` or whatever discovery
returns), a Loki stream selecting it.

Also absent from this stack: `gcx assistant` and investigations — Grafana
Cloud features the local anonymous instance does not serve.
