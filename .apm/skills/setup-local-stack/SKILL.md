---
name: setup-local-stack
description: Configure gcx against the local oddyssey Grafana stack and query its four signals (metrics, traces, logs, profiles) without touching the user's own gcx contexts. Owns the global configuration's "local" stack value. Use when the configured stack is "local", when querying the local stack (Grafana host port from the global configuration, default 3000), when configuring gcx locally, when a command needs the Tempo, Prometheus, Loki, or Pyroscope datasource UID. gcx is the mandatory query CLI for the stack - install it if missing (brew install gcx, or the official install script from github.com/grafana/gcx).
---

# gcx on the local oddyssey stack

The local stack is a single otel-lgtm container: Grafana, OTLP (gRPC and
HTTP), Pyroscope's ingest endpoint, and four datasources — Tempo,
Prometheus, Loki, Pyroscope — behind the Grafana datasource proxy. The
host ports come from the **global configuration** (defaults `3000` /
`4317` / `4318` / `4040`): read the effective URLs from `odd_stack_up`'s
result (`grafana_url`, `otlp_endpoint`) or `odd_config_get` — never
assume the defaults, and point an application's
`OTEL_EXPORTER_OTLP_ENDPOINT` at those values, never at a hardcoded
port. Profiles are the one signal that does not arrive over OTLP:
pyroscope-io-style SDKs push over Pyroscope's own HTTP protocol,
straight to `http://localhost:<local.pyroscope_port>` (issue #224) —
discover that port from `odd_config_get` the same way. Grafana serves its API **anonymously** here: no credentials are
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

**Read by section.** The caller's preflight (`check-backend-configuration`)
writes the isolated context below and proves it, and hands its path
over in the mission block; an agent holding that handoff skips
`## Configure an isolated context` (regenerate the file only when
`gcx config check` fails on it) and reads `## Datasources` and
`## This stack is push-based` — the two sections a query needs.

## Configure an isolated context

Never edit the user's own gcx configuration. Point `GCX_CONFIG` at a
**stable per-session path** — stable so the file is written once and
reused while the configured ports stay the same, isolated so the
user's contexts stay untouched. Read the effective `grafana_url` from
`odd_config_get` (or `odd_stack_up`'s result) **before** writing the
file, and put that URL — not the default — on the `server:` line:

```bash
export GCX_CONFIG="${TMPDIR:-/tmp}/oddyssey/gcx-local.yaml"
mkdir -p "$(dirname "$GCX_CONFIG")"
cat > "$GCX_CONFIG" << 'EOF'
current-context: local
contexts:
  local:
    grafana:
      server: http://localhost:3000   # the configured grafana_url (odd_config_get) - never assume this default
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

**A port change invalidates the whole file — regenerate it, never
edit it in place.** gcx binds each stored credential to a keychain
entry keyed by the config source and destination: after the
configured ports change (`odd_config_set`), patching the `server:`
line leaves the credential bound to the old destination and gcx
rejects it before any network use:
`Configured credential "stack:local" field "grafana-password" was
rejected before network use: the keychain reference does not match
this config source, owner, field, and destination` — and the
suggested re-authenticate is a dead end on this anonymous stack.
Delete the file and rewrite it whole from the block above with the
new `grafana_url`: the fresh inline credential creates a new binding,
and `gcx config check` passes on the new port (verified in both
directions, 3000 → 3001 → 3000).

The four `default-*-datasource` entries make the `-d` flag unnecessary; the
commands below keep it for explicitness, but it can be dropped.

Each shell invocation starts fresh, so `export GCX_CONFIG=...` again in every
command block (or prefix the command with it) — the file itself persists, so
the write and `gcx config check` happen only once per session — unless
the configured ports change, which invalidates the file (above) and
forces a full rewrite. If gcx
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

This table holds for **gcx v1.0.0 or newer** (verified against v1.0.0
and Grafana 13.1.3) — package managers may ship older builds, so check
`gcx --version` before trusting it. The gcx
command surface moves between versions, so when a documented command
errors, trust `gcx <group> --help` over this table.

gcx is the stack's mandatory **query** CLI — explore and measure
through it. Recording raw datasource-proxy HTTP in a report
(`/api/datasources/proxy/uid/<uid>/...` URLs) is
the right form for **replayable evidence**: a proxy URL replays
verbatim with curl alone, on a machine with no gcx context. Query with
gcx; record a proof query in whichever form the verify run can replay
exactly — both are contract-conform, and the report says which was
used.

Discover before you query: `gcx metrics labels` / `gcx metrics metadata`,
`gcx traces labels`, `gcx logs labels`, `gcx profiles list-profile-types`.
The four signals' discoveries are independent — **run them as your own
parallel tool calls in one turn**, not serially; the same holds for the batch of
`gcx traces get` fetches once a search has returned its trace IDs.
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
