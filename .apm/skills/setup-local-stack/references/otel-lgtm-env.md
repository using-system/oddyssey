# The otel-lgtm environment surface

Environment variables are the container's **only** configuration surface,
and `odd_stack_up` / `odd_stack_reset` (`env` parameter) are how they
reach it. This catalog is built from the pinned image's own tag —
**`grafana/otel-lgtm:0.31.0`** (its README and `docker/run-*.sh`
scripts) — and must be re-validated on every pin bump; when the pin and
this file disagree, trust the tag.

Contract reminders (they apply to every variable below):

- env applies at **container creation only**: on `odd_stack_up` over an
  existing container the result says `env_applied: false` and nothing
  landed — a reset (wipes all telemetry) is the way to apply it;
- the embedded default `PROMETHEUS_EXTRA_ARGS=--enable-feature=otlp-deltatocumulative`
  is merged in; a user entry with the same key **overrides** it (dropping
  delta-metric ingestion — CLI coding agents' `claude_code.*` metrics
  need it, so extend rather than replace);
- once applied, env is **sticky**: `odd_config_set`'s auto-reset carries
  it forward (`env_preserved`, key names only) until a bare
  `odd_stack_reset` clears it;
- values may hold secrets (`OTEL_EXPORTER_OTLP_HEADERS`): refer to them
  by name in reports, never quote values.

## Per-component debug logs — `ENABLE_LOGS_*`

`ENABLE_LOGS_GRAFANA`, `ENABLE_LOGS_LOKI`, `ENABLE_LOGS_PROMETHEUS`,
`ENABLE_LOGS_TEMPO`, `ENABLE_LOGS_PYROSCOPE`, `ENABLE_LOGS_OTELCOL`,
`ENABLE_LOGS_OBI`, `ENABLE_LOGS_ALL` (`=true`).

The right lever to see a component's own output in `docker logs
oddyssey-lgtm` — NOT `GF_LOG_LEVEL`, whose output stays swallowed unless
`ENABLE_LOGS_GRAFANA` is on. Unrelated to application logs (those flow
through OTLP into Loki). Since v0.31.0 a component that dies before
readiness fails the startup fast and the error itself recommends the
matching `ENABLE_LOGS_<component>` — turning it on is the first
diagnostic step for a stack that will not come up.

## Backend tuning — `*_EXTRA_ARGS`

| Variable | Example (from the tag) | Use case |
| --- | --- | --- |
| `PROMETHEUS_EXTRA_ARGS` | `--storage.tsdb.retention.time=90d` | retention; carries the embedded delta default — extend, do not replace |
| `LOKI_EXTRA_ARGS` | `-store.retention=90d -compactor.retention-enabled=true -compactor.delete-request-store=filesystem` | log retention (the three flags go together) |
| `TEMPO_EXTRA_ARGS` | `--query-frontend.mcp-server.enabled=true` | Tempo's own MCP server on the query frontend |
| `PYROSCOPE_EXTRA_ARGS` | — | profile backend flags |
| `OTELCOL_EXTRA_ARGS` | — | collector flags (see also `OTEL_COLLECTOR_DEBUG_EXPORTER=true` for a debug exporter) |

Retention matters little on this stack (no volume, a reset wipes
everything anyway); the interesting entries are behavioral ones like
Tempo's MCP server.

## OTLP forwarding — dual-write to a remote backend

`OTEL_EXPORTER_OTLP_ENDPOINT` (all signals, OTLP/HTTP, scheme required —
e.g. `https://otlp-gateway-<zone>.grafana.net/otlp`),
`OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` / `_METRICS_ENDPOINT` /
`_TRACES_ENDPOINT` (per-signal, take precedence),
`OTEL_EXPORTER_OTLP_HEADERS` (authentication — secret, name only).

Set on the container, these make the **embedded collector** forward
everything it receives to a remote backend while still writing locally:
one telemetry stream feeds the local ODD loop AND a remote mirror
(e.g. Grafana Cloud) at once. The most ODD-significant capability of the
whole surface.

## eBPF auto-instrumentation — OBI

`ENABLE_OBI=true`, `OBI_TARGET` (`java`, `python`, `node`, `dotnet`,
`ruby`, or a regex), `OTEL_EBPF_OPEN_PORT` (port list override).

Generates traces and RED metrics for HTTP/gRPC services with zero code
changes — a pre-instrumentation observation baseline. **Caveat: not
reachable through `env` alone on this stack.** OBI needs Linux (kernel
5.8+, BTF) and the `--pid=host --privileged` docker flags, which the
embedded container definition does not pass — it requires the manual
`docker run` escape hatch documented in the skill, and a reset recreates
the container without those flags.

## Grafana — `GF_*`

Any Grafana setting via `GF_*`. Documented in the tag: `GF_PLUGINS_PREINSTALL`
(pre-install plugins), `GF_SECURITY_ADMIN_USER` / `GF_SECURITY_ADMIN_PASSWORD`,
`GF_AUTH_ANONYMOUS_ENABLED` / `GF_AUTH_ANONYMOUS_ORG_ROLE`,
`GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH` (custom home dashboard).

The stack serves Grafana **anonymously** by design and the isolated gcx
context depends on it: disabling anonymous auth breaks the skill's
context template until credentials are added there too.

## Lifecycle and debug

- `LGTM_SHUTDOWN_TIMEOUT_SECONDS` — grace period (default 5 s) before
  still-running components are forcefully stopped on SIGTERM/SIGINT.
- `OTEL_COLLECTOR_DEBUG_EXPORTER=true` — adds the collector's debug
  exporter, printing received telemetry to the component logs (pair with
  `ENABLE_LOGS_OTELCOL=true`).
