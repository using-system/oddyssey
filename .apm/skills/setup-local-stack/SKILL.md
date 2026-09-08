---
name: setup-local-stack
description: Configure gcx against the local oddyssey Grafana stack and query its four signals (metrics, traces, logs, profiles) without touching the user's own gcx contexts. Owns the global configuration's "local" stack value. Use when the configured stack is "local", when querying the local stack (Grafana host port from the global configuration, default 3000), when configuring gcx locally, when a command needs the Tempo, Prometheus, Loki, or Pyroscope datasource UID. gcx is the mandatory query CLI for the stack - install it if missing (brew install gcx, or the official install script from github.com/grafana/gcx).
---

# gcx on the local oddyssey stack

One otel-lgtm container: Grafana, OTLP (gRPC and HTTP), Pyroscope's
ingest port, and four datasources behind the Grafana datasource proxy.
Bring it up with the oddyssey MCP tools (`odd_stack_status`,
`odd_stack_up`) before configuring anything here.

## Configure an isolated context

```bash
python3 <this skill's directory>/scripts/gcx_local.py
```

It takes no arguments but `--json`. It reads the host ports from the
global configuration — never assumed, never hardcoded — writes an **isolated** context at a stable path so the
user's own gcx contexts stay untouched, and proves it with `gcx config
check`. It prints the `export GCX_CONFIG=...` line to put in front of
every later gcx call, the four datasource UIDs, and the OTLP and
Pyroscope endpoints an instrumented service should target. `--json` for
the same, parseable.

Exit 0 means gcx reached the stack. Exit 1 says which step failed: gcx
missing (install it — `brew install gcx`, or the official script from
github.com/grafana/gcx), or the stack unreachable (`odd_stack_up`).

Re-run it after any port change. It rewrites the file whole on purpose:
gcx binds a stored credential to its destination, so patching the
`server:` line in place leaves the binding stale and gcx refuses it
before any network use.

## Inventory the services, in one command

```bash
python3 <this skill's directory>/scripts/probe_services.py <svc> [<svc> ...] --since 30m
```

One call answers what every observation asks before it drives anything:
per service, which of the four signals carries it and under which
identity (instances, environment, version, SDK), the operations its
traces name, the metrics it publishes, and the current reading of every
cumulative series — the baseline a later query subtracts from. Absence is
reported as loudly as presence: a signal that is genuinely missing is a
result, not a failed probe.

**All the services in one call** — the script probes them concurrently,
so one call for three is one call, and three calls are three:

```bash
GCX_CONFIG=<the path gcx_local.py printed> \
  python3 <this skill's directory>/scripts/probe_services.py svc-a svc-b svc-c --since 30m
```

That is the whole surface, so `--help` has nothing to add and the file
has nothing to read: service names are positional and the only required
argument, `--since <window>` sets the lookback (default `30m`), `--json`
prints the same report parseable, `--no-baseline` skips the counter
readings. Nothing else.

**Do not write these queries by hand.** Service names and a window
determine every one of them, so there is no judgment to exercise: the
script runs them concurrently and returns a synthesis in about a second,
where the same work spelled out call by call costs minutes and buries
the answer in raw JSON.

Exit 0 means every probe ran; exit 2 means at least one failed, and the
line marked `!` names it.

## Datasources

| Signal | Backend | UID | Query with | Language |
| --- | --- | --- | --- | --- |
| Traces | Tempo | `tempo` | `gcx traces labels/query/get -d tempo` | TraceQL |
| Metrics | Prometheus | `prometheus` | `gcx metrics labels/series/metadata/query` | PromQL |
| Logs | Loki | `loki` | `gcx logs labels/series/query` | LogQL |
| Profiles | Pyroscope | `pyroscope` | `gcx profiles list-profile-types/labels/query -d pyroscope` | profile selector |

Verified against gcx v1.0.0 and v1.2.0, Grafana 13.1.3 and 13.2.0, all
four signals round-tripped. The gcx command surface moves between
versions: when a documented command errors, trust `gcx <group> --help`
over this table.

Discovery across the four signals is what `probe_services.py` above
already ran — read its output rather than re-deriving it. Past it, the
queries are the `observability-cli-guides` skill's `grafana-*` scripts,
named per signal in `grafana.md`'s `## Query by signal`: what a window
holds, per-operation latency with its exemplars fetched, the span tree of
a trace, exact log counts and severities, top profile frames. They run
their gcx calls concurrently on their own, so one invocation is one tool
call — **never a batch script of `gcx` calls backgrounded with `&` and a
`wait`**, and never one gcx call per tool call: a run that writes that
runner is rebuilding a shipped script. `gcx metrics series` and
`gcx logs series` are not discovery commands — bare, they error; both
need at least one selector — and the scripts pass one.

## This stack is push-based

**It is push-based.** Nothing is scraped, so `up{job="<service>"}` is
empty for every service, healthy or not — it proves nothing. Prove a
service is present with its own data: a Tempo search for
`{resource.service.name="<svc>"}`, a Prometheus series carrying it
(`target_info{service_name="<svc>"}`), a Loki stream selecting it.

**Profiles carry no instance identity.** Their labels are
`service_name`, `deployment_environment`, `otel.scope.*`,
`process.runtime.*` — no `service.instance.id` equivalent, so two
processes sharing a service name merge into one flamegraph. Launch a
driven service with a per-run profiler tag mirroring the OTel attribute
(`service_instance_id=<run slug>`, through the SDK's own `tags`), and
qualify profile selectors by it; without one, say so rather than
implying the profile is the run's.

**Tempo's metrics-generator series carry none either.** Their labels are
the generator's own (`service`, `span_name`, `span_kind`, `status_code`,
`client`, `server`, `le`); `__metrics_gen_instance` names the generator,
not the observed process. Read them for shape and topology; take a run's
counts and latencies from the service's own OTel histogram qualified by
`service_instance_id`.

**And it is not Grafana Cloud**: `gcx assistant` and investigations are
not served here.

## Configuring the container

The image is configured exclusively through environment variables passed
to `odd_stack_up`/`odd_stack_reset`, and they apply **at container
creation only** — a container predating the current oddyssey version
keeps its definition until its next reset. An applied env is persisted
into `stack_config.local` and reapplied on every later recreation, so it
survives resets without being repeated; credential-named variables are
applied but never persisted, and must be passed again each time. The
image's full variable surface is
[`references/otel-lgtm-env.md`](references/otel-lgtm-env.md), aligned on
the pinned tag.

The stack holds **no volume by design**: a reset wipes everything, and
the observation report is the only durable artifact. For what env cannot
express (volumes, networks), the escape hatch is a manual `docker run`
reusing the same name and ports — `status`/`up`/`down` keep working
against it, but a **reset recreates the container from the embedded
definition** and hand-mounted volumes do not survive it.

## Recording a query as evidence

Query through gcx. For a proof query a verification run must replay
verbatim, the raw datasource-proxy URL
(`/api/datasources/proxy/uid/<uid>/...`) is the right form — it replays
with curl alone, on a machine with no gcx context. Both are
contract-conform; the report says which was used.
