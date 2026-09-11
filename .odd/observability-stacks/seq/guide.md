---
stack: seq
stack_config_fields: []
verified: 2026-09-11, seqcli 2026.1.2616 against Seq 2026.1.17114 (the repository's docker-compose/seq, no API key) - every script invocation below run over the built-in sample data (seqcli sample ingest, the Roastery applications, window 2026-09-11T07:15:00Z..07:20:00Z, 2 981 events, 355 metric points; the discover environment probe also over 07:25-07:30 and 07:50-08:00); logs, traces and metrics exercised, profiles not served; the authentication-failure shape of the connection proof, the install commands and a @Resource-carrying (OTel-fed) instance were not exercised (marked below)
---

# Seq

[Seq](https://datalust.co/seq) is a structured log, trace and metric
server: every log event and every span is one JSON document (`@t`,
`@mt`, `@l`, its own properties; a span adds `@st`, `@sk`, `@ps`),
queried with a SQL-like language; metric points are a separate
`series` stream. It is queried with `seqcli`, the official command-line
client, and this stack ships the scripts a run invokes so that it
composes no `seqcli` command by hand. This file follows the
`observability-cli-guides` reference contract: the preflight and the
switch read the four configuration sections, the agents the rest.

## CLI binary

- **Binary**: `seqcli`
  ([command-line client](https://datalust.co/docs/command-line-client)).
- **Detect**: `seqcli version || "$HOME/.dotnet/tools/seqcli" version`
  (prints the client version; exit 0). Installed as a dotnet global
  tool it lives in `~/.dotnet/tools`, which is not always on `PATH`;
  the scripts below look on `PATH` first, then there, so a run passes
  no path - verified 2026-09-11 with the binary absent from `PATH`.
- **Install**, one method only (from the documentation, not run
  2026-09-11 - the tool was already installed):
  - dotnet global tool: `dotnet tool install --global seqcli` (needs
    the .NET SDK), or
  - a platform binary from the
    [releases page](https://github.com/datalust/seqcli/releases), or
  - the container: `docker run --rm datalust/seqcli:latest <command>`
    (reach a Seq on the same machine by its IP, not `localhost`).

## Setup

`seqcli` carries its own connection, like a CLI context: `SeqCli.json`
holds the server URL and, when the instance authenticates, the API key
([configuration](https://datalust.co/docs/command-line-client)). The
user sets them, never an agent:

```text
seqcli config set -k connection.serverUrl -v http://localhost:5341
seqcli config set -k connection.apiKey -v <api key>      # only when the server authenticates
```

A fresh install already points at `http://localhost:5341`. The
environment variables `SEQCLI_CONNECTION_SERVERURL` and
`SEQCLI_CONNECTION_APIKEY` override the file for one shell (the URL
override verified 2026-09-11). The API key is a credential: it stays in
`SeqCli.json` or in that variable, referred to by name, never written
here. An instance started without authentication (the repository's
`docker-compose/seq` does that, local use only) needs no key.

## Query by signal

The signals are read with the scripts this stack ships under
`scripts/` - never with `seqcli` commands composed by hand. The shared
module `scripts/seq_cli.py` carries, in code, every trap verified
2026-09-11: the binary off `PATH`; `search -c` defaulting to **1**; a
malformed `-f` filter printing nothing with exit 0 (re-validated
through `query`, which reports the syntax error); the three `query`
shapes (`Rows`; `Slices` on `group by time(...)`; `Series` of `Slices`
on `group by <prop>, time(...)`); `order by` refusing an aggregate
without an `as` alias; `@Elapsed` and its percentiles in **100 ns
ticks** (divided by 10 000 into ms); `@t` printed in the server's local
offset while `@st` is UTC; `node health` printing the bare word
`Unreachable` with exit 1; a histogram metric aggregating to a bucket
object. Each invocation below is copy-pasteable from the observed
repository's root and states the script's **whole** flag surface:
`--help` has nothing to add and the files have nothing to read. A run
that lacks a shape of the work records it in its report's `## 8. Stack
friction`, never a wrapper.

Common to every script: it hits the instance `seqcli`'s own
configuration names (`## Setup`); a **window** is `--from <RFC3339 UTC>
--to <RFC3339 UTC>` or `--since <duration>` (a lookback ending now,
`30m`, `2h`); a **service** is `--service <value>` (repeatable, none =
every service) matched on `--service-key <property>` (default
`Application`, the sample data's name; an OTel-instrumented service
names itself in `@Resource.service.name`, pass that); `--json` prints
the same result as one object carrying the keys the `Output` line
names plus `commands` (the seqcli calls) and `error` (empty on
success); exit 0 means every query ran (an empty answer is a result),
exit 1 that seqcli errored - **and then the only line printed is the
error**; a usage error exits 2. **Every subcommand ends by printing the
seqcli commands it ran** - `queries run (record these):` - and those
lines, with the script invocation above them, are what the report
records as the query. The scripts run their calls **concurrently**
against one configuration - verified 2026-09-11, eight `query` calls
side by side, all complete. The commands behind the scripts are
`seqcli search`, `seqcli query`, `seqcli trace`, `seqcli metrics
search|dimensions` and `seqcli node health`
([command reference](https://datalust.co/docs/command-line-client)),
filters in the
[Seq query language](https://datalust.co/docs/the-seq-query-language),
aggregates in [SQL queries](https://datalust.co/docs/sql-queries),
`@`-names in
[built-in properties](https://datalust.co/docs/built-in-properties-and-functions).

### First, in one call: what the window holds - and where the environment is read from

```bash
python3 .odd/observability-stacks/seq/scripts/seq-discover.py --from <start> --to <end>
python3 .odd/observability-stacks/seq/scripts/seq-discover.py --service <svc> --since 30m --json
```

Whole surface: `--service` / `--service-key`, a window, `--bucket
<duration>` (the slice the data distribution is reported in, default
`1m`), `--sample N` (the newest events whose property names are
inventoried, default 200), `--json`. **This is the first read of a
window**: it carries the deployment-environment detection and the GenAI
presence probe, so a run composes neither. Output: `signals` (log-event,
span and metric-point totals; `profiles: not served`), `data_slices`
(the slices that hold events - **where a sparse window's data sits**,
read before any narrower query), `environment` (`resource_events` - how
many events carry a `@Resource` object; `resource_identities` -
`none`, or `per service` when the rows below name one;
`environment_properties` - the count of each environment-naming
property present among `Environment`, `EnvironmentName`,
`MachineName`, `host.name`, `deployment.environment.name`, `Origin`;
`gen_ai_events` - events carrying a `gen_ai.*` attribute on the event
or its resource, the GenAI section runs when it is non-zero;
`read_from` - the one place a run reads the environment from: the
resource when any event carries one, else the properties present, else
`nothing`), `environment_values` (the distinct values of each
environment-naming property present, 20 at most), `sampled_keys` (the
property names the newest `--sample` events carry, with counts - the
inventory of what the store really holds, `@`-keys included), per
service `logs`, `spans`, `traces` (distinct trace ids), `levels`,
`exceptions`, `root_operations` (root spans by `@MessageTemplate`, the
span's name), `metric_points`, `resource_events`,
`resource_identities` (one row per distinct `service.name`,
`service.instance.id`, `deployment.environment.name`,
`service.version` of its `@Resource`, with the event count),
`environment_properties`, `gen_ai_events`; `metric_definitions` (name,
kind, unit); `failed` (exit 2 when non-empty). A service the window
names by no value of the key is reported as `(no value)` - the sample's
API-layer events are (269 in the first window). Runs nine `query`, one
`metrics search` and one `search` concurrently, plus one `distinct`
query per environment-naming property present.

- OTLP resource attributes are collected into the `@Resource` object
  every event carries, and dotted attribute names are **unflattened
  into nested objects** - `service.name` is `@Resource.service.name`, a
  `gen_ai.system` event attribute is `gen_ai.system`
  ([ingestion with OpenTelemetry](https://datalust.co/docs/ingestion-with-opentelemetry));
  the script probes the nested path and, for `gen_ai`, the flat
  `@Properties['gen_ai.system']` a pre-2024.1 ingestion would have
  stored. **Never `has(['x'])`**: a bare `['x']` is an array literal
  and `has()` of it is true on every event (2 981 of 2 981, verified
  2026-09-11) - the hand-composed GenAI probe that used it reported
  GenAI everywhere.
- Verified 2026-09-11 on the three windows the store held
  (07:15-07:20, 07:25-07:30, 07:50-08:00 UTC, sample data): no event
  carries a `@Resource` or a `@Scope` (`resource_events=0`,
  `resource_identities: none` - the script says `none`, never errors),
  `Origin` is the only environment-naming property present (every
  event, one value, `seqcli sample ingest`), `gen_ai_events=0`. An
  instance fed by an OTel SDK, where `@Resource` is present, is
  unverified 2026-09-11 - the identity query ran and returned no rows,
  its shape on data is the documentation's.

### Logs

```bash
python3 .odd/observability-stacks/seq/scripts/seq-logs.py count --service <svc> --from <start> --to <end>
python3 .odd/observability-stacks/seq/scripts/seq-logs.py sample --level Error --contains "deadlock" --spans --since 30m --show 20
python3 .odd/observability-stacks/seq/scripts/seq-logs.py sample --filter "StatusCode >= 500" --service <svc> --from <start> --to <end>
python3 .odd/observability-stacks/seq/scripts/seq-logs.py correlate --service <svc> --from <start> --to <end> --json
```

Whole surface: every subcommand takes `--service` / `--service-key`, a
window, `--json`; `sample` adds `--level <@Level value>` (exact, e.g.
`Error`), `--contains <text>` (case-insensitive substring of the
message or the exception - rewritten as `like '%..%' ci`, the one form
both `search -f` and `query -q` accept), `--filter <Seq filter>`
(and-ed in, any expression of the query language), `--spans` (include
span events; log events only by default), `--show N` (events printed,
default 20 - the search's `-c`).

- `count` - Output: per service `lines`, `levels` (log events by
  `@Level`), `exceptions`, and `span_levels` / `span_exceptions` for
  its spans. **A request's level and exception land on its span, not
  on a log event**: on the sample the 8 errors are all spans, the log
  events carry none (verified 2026-09-11) - read the span line before
  calling a service error-free.
- `sample` - Output: `matching` (the exact count of the filter),
  `samples` (each with `ts` in UTC, `level`, `trace_id`, `span_id`, the
  rendered `message`, the first line of the `exception`, the event's
  `properties`), newest first. Verified 2026-09-11: `--level Error
  --contains deadlock --spans` 6 matches; `--filter "StatusCode >=
  500"` 5; a malformed `--filter` exits 1 with the server's syntax
  error, once.
- `correlate` - Output: per service `lines`, `with_trace_id`,
  `without`, and `orphan_samples` (ten events without a trace id). On
  the sample the batch job's 29 events and 18 route-binding lines are
  the orphans (verified 2026-09-11) - classify before calling it a gap.

### Traces

Spans are events: `@sp` (span id), `@tr` (trace id), `@ps` (parent),
`@st` (start, UTC), `@sk` (kind) in the JSON; `@SpanId`, `@TraceId`,
`@ParentId`, `has(@Start)`, `@SpanKind`, `@Elapsed` in filters
([traces in Seq](https://datalust.co/docs/getting-traces-into-seq),
[built-in properties](https://datalust.co/docs/built-in-properties-and-functions)).
Seq derives no RED series from spans: the per-operation table is built
from the root spans' `@Elapsed` percentiles, which these scripts do.

```bash
python3 .odd/observability-stacks/seq/scripts/seq-traces.py operations --service <svc> --group-by RequestMethod --group-by <templated route property> --from <start> --to <end>
python3 .odd/observability-stacks/seq/scripts/seq-traces.py exemplars --above 100ms --service <svc> --from <start> --to <end> --show 10
python3 .odd/observability-stacks/seq/scripts/seq-traces.py children --service <svc> --from <start> --to <end>
python3 .odd/observability-stacks/seq/scripts/seq-traces.py trace <trace id>
```

Whole surface: `operations`, `exemplars` and `children` take
`--service` / `--service-key`, a window, `--all-spans` (every span
instead of the root spans only - those without a `@ParentId`), `--kind
<@SpanKind value>` (`Server`, `Client`, `Internal`, `Producer`,
`Consumer`), `--json`; `operations` and `children` add `--group-by
<property>` (repeatable, default `@MessageTemplate` - the span's name);
`operations` adds `--min-count N` (default 1); `exemplars` adds
`--above <duration>` (a Seq duration literal, `100ms`, `1s`, or a
number of 100 ns ticks; default 0), `--filter <Seq filter>` (and-ed
in), `--show N` (default 10); `trace` takes the trace id, `--no-logs`
(spans only), `--json`.

- `operations` - Output: one row per service and group - `count`,
  `errors` (`@Level = 'Error'` spans), `p50_ms`, `p95_ms`, `p99_ms`,
  `max_ms` (ticks converted). **Group by the whole operation**: the
  method and the **templated** route together - one half folds
  distinct operations into one row, and a concrete path (the sample's
  `RequestPath` carries the order id) shatters one operation into a row
  per request. The sample's root spans carry `RequestMethod` and
  `RequestPath` only (its `RouteTemplate` sits on a log event), so the
  templated grouping was verified on the sample with `--group-by
  RequestMethod --group-by RequestPath --min-count 5` (four rows) and
  by the default template (one row, 410 spans, p99 189 ms) -
  2026-09-11; on an OTel-instrumented service the route property is
  the service's own (`http.route` under its resource or attributes) -
  discover it with `sample --spans` first.
- `exemplars` - Output: `matching` (the exact count above the
  threshold), `exemplars` (each with `trace_id`, `span_id`,
  `parent_id`, `start`, `end`, `elapsed_ms` computed from `@t - @st`
  with both offsets honoured - verified equal to `seqcli trace`'s
  `elapsedMs` to the microsecond, 2026-09-11 -, `kind`, `level`, the
  rendered `message`, `properties`), slowest first among the newest
  `--show` matches. **The search returns the newest matches, not the
  slowest**: raise `--above` to reach the tail (a p99 read from
  `operations` is in ms; `--above 189ms` is the literal to paste).
- `children` - Output: the non-root spans by group - `count`, `traces`
  (distinct), `calls_per_trace`, `p50_ms`, `p99_ms`, `max_ms` - the
  downstream call count per request (verified 2026-09-11: 1 014 SQL
  spans over 410 traces, 2.47 per request).
- `trace` - Output: `summary` (`root`, `duration_ms`, `spans`, `logs`,
  `errors`, `longest`), `nodes` (depth-first, `type` span or log,
  `elapsed_ms`, `level`, `message`, `exception`), `complete`. An
  unknown id exits 1 with `No events found for trace <id>` (verified
  2026-09-11).

### Metrics

Seq stores OTLP metrics as a `series` stream: one point per timestamp,
resource and attribute set, the metric's name, kind, unit and
description in `@Definitions`, its value in a property named after it
([metrics](https://datalust.co/docs/metrics),
[metrics from OpenTelemetry](https://datalust.co/docs/metrics-from-opentelemetry-sdks)).
Verified 2026-09-11 on the sample's 12 definitions (Gauge, Sum and
Exponential kinds) - the earlier stack file had never exercised them.

```bash
python3 .odd/observability-stacks/seq/scripts/seq-metrics.py list --service <svc> --from <start> --to <end>
python3 .odd/observability-stacks/seq/scripts/seq-metrics.py query <metric> --group-by <dimension> --from <start> --to <end>
python3 .odd/observability-stacks/seq/scripts/seq-metrics.py query <metric> --agg mean --group-by <dimension> --step 1m --since 30m --json
```

Whole surface: both subcommands take `--service` / `--service-key`, a
window, `--json`; `query <metric>` adds `--agg mean|max|min|sum|last|count`
(default by kind: Gauge `mean`, Sum `sum`, Exponential `max`),
`--group-by <dimension>` (repeatable), `--step <duration>` (time
slices; one row per group without it).

- `list` - Output: `metrics`, each with `name`, `kind`, `unit`,
  `description`, `dimensions` (the accessors `metrics dimensions -m`
  lists). Runs `metrics search` once and one `metrics dimensions` per
  definition, concurrently.
- `query` - Output: `rows`, each with `group` (the dimension values),
  `time` (with `--step`), `value` - a number, or for a histogram
  (`Exponential` kind) `{count, min, max, p50, p95, p99}`: **`mean` and
  `percentile` on a histogram are null server-side**; `max` returns the
  merged bucket object and the quantiles are read off its bucket
  midpoints (approximate, the bucket's resolution) - verified
  2026-09-11 on `HttpRequestDuration --group-by StatusCode` (four
  rows), `BeanTemperature --agg mean --group-by MachineId --step 2m`,
  `OrderCreated --step 1m` (5, 46, 22, 31). An unknown metric is an
  empty row, not an error.

### Profiles

Not served: Seq stores no profiling data. A mission that needs
profiles says so and moves on.

### Residual traps, for a call still composed by hand

- Windows go through `--start`/`--end` only: a `where @Timestamp >=
  '<iso>'` compares a string and silently matches nothing (2026-09-11).
- `search --json` prints newest first; `-c` pages transparently
  (`-c 3000` returned the window's 2 981 events in one call).
- Double-quoted text fragments (`"deadlock"`) are accepted by
  `search -f` and refused by `query -q`; `like '%x%' ci` works in both
  and `like` is case-sensitive without `ci`.
- A string literal is single-quoted, a quote inside it doubled
  (`'it''s'`); `<prop> in ['a', 'b']` is the service selector.
- `seqcli tail` streams until interrupted and `seqcli sample ingest`
  writes to the store: neither is a query, a mission never runs them.

## Planning notes

- Seq is a log, trace and metric store: profiles absent - plan on the
  three, say which the service emits (`seq-discover.py` says).
- Structured properties are the way in: `discover` and `sample --spans`
  first, then the operation grouping on the properties the service
  actually emits - the whole operation, never one half of it.
- The deployment environment is read where `discover`'s `read_from`
  says - `@Resource.deployment.environment.name` on an OTel-fed
  instance, an `Environment`-like property otherwise; on the sample
  data it names `Origin`, whose one value marks the generator, not an
  environment - a run states that, it does not invent one. The GenAI
  section runs only when `gen_ai_events` is non-zero.
- Spans carry the request's level, exception and status: an error
  budget is read off the spans (`operations` `errors`, `count`'s span
  line), not off the log events.
- `@SpanKind` was `Internal` throughout the sample (2026-09-11) - on an
  OTel-instrumented service `--kind Server` selects the entry spans.
- The sample data (`seqcli sample ingest`) is the verification
  baseline; a real service's events differ in shape - discover before
  asserting. Unverified 2026-09-11: `--service-key
  @Resource.service.name` on a service that sets it (the grouping ran,
  the sample carries no resource - every row was `(no value)`).
- Verification dates: every invocation above 2026-09-11 unless its
  bullet says otherwise (the install commands, the authentication
  failure below).

## Configuration display

### Display

```bash
python3 .odd/observability-stacks/seq/scripts/seq-context.py
```

Whole surface: `--json`. Prints the binary and where it was found
(`PATH` or `~/.dotnet/tools`), the client version, the server URL and
its source (`SEQCLI_CONNECTION_SERVERURL` when set, else `SeqCli.json`
`connection.serverUrl`), whether an API key is configured - `set` or
`not set`, by name (`SEQCLI_CONNECTION_APIKEY` or `connection.apiKey`),
**its value never printed** -, the health verdict and the server
version. Never echo `connection.apiKey`, `SEQCLI_CONNECTION_APIKEY`, or
any `-a` value; `seqcli config list` prints the key's field, do not run
it for the display.

### Connection proof

The same `seq-context.py` call: exit 0 when `seqcli node health --json`
answered `"status":"healthy"` (verified 2026-09-11, Seq 2026.1.17114).
Exit 1 with `Unreachable` means the server does not answer at the
configured URL (verified 2026-09-11 against a closed port: seqcli
prints the bare word and exits 1); exit 127 means seqcli is not
installed. An authentication error (the instance needs an API key)
surfaces as the command's error - shape unverified 2026-09-11, the
instance runs without a key. Either way the fix is the user's, in
`## Setup`: point `connection.serverUrl` at the instance, put the key
into `connection.apiKey` - never done for them.

### Change-request phrasing

- "switch to seq", "use Seq", "point the runs at my Seq"

## What to persist

### What stack_config holds

Nothing: `seqcli`'s own configuration names the instance and holds the
key (`## Setup`), like a CLI context. The frontmatter declares an empty
field list, and `stack_config.seq` stays `{}` - not configured, the
correct final state.

### Where each value comes from

Not applicable - the server URL lives in `SeqCli.json`, set by the
user with `seqcli config set -k connection.serverUrl -v <url>`.

### What to ask the user

Nothing to persist. When the connection proof fails, ask them to run
the `## Setup` commands - the URL their Seq answers on (the UI's
address, the same port serves the API; `http://localhost:5341` for the
repository's `docker-compose/seq`), and the API key by name only.
