---
stack: seq
stack_config_fields: []
verified: 2026-09-04, seqcli 2026.1 against Seq 2026.1 in Docker (docker-compose/seq) - logs and traces from the built-in sample data; metrics not exercised
---

# Seq

[Seq](https://datalust.co/seq) is a structured log and trace server:
every event is a JSON document with `@t`, `@mt`, `@l` and its own
properties, queried through a SQL-like language. It is queried with
`seqcli`, the official command-line client. This file follows the
`observability-cli-guides` reference contract; the preflight and the
switch read the four configuration sections, the agents the rest.

## CLI binary

- **Binary**: `seqcli` ([command-line client](https://datalust.co/docs/command-line-client)).
- **Detect**: `seqcli version || "$HOME/.dotnet/tools/seqcli" version`
  (prints the client version; exit 0). Installed as a dotnet global
  tool it lives in `~/.dotnet/tools`, which is not always on `PATH` —
  the second half finds it there; when it does, every command below
  needs the same full path or `PATH` extended.
- **Install**, one method only:
  - dotnet global tool: `dotnet tool install --global seqcli`
    (needs the .NET SDK), or
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
seqcli config -k connection.serverUrl -v http://localhost:5341
seqcli config -k connection.apiKey -v <api key>      # only when the server authenticates
```

A fresh install already points at `http://localhost:5341`. The
environment variables `SEQCLI_CONNECTION_SERVERURL` and
`SEQCLI_CONNECTION_APIKEY` override the file for one shell. The API key
is a credential: it stays in `SeqCli.json` or in that variable,
referred to by name, never written here. An instance started without
authentication (the package's `docker-compose/seq` does that, local use
only) needs no key.

## Query by signal

Every command below hits the instance `seqcli`'s own configuration
names (`## Setup`); the preflight handoff's `Target:` line says which.
`--json` prints newline-delimited JSON, one event or one result set per
line; `--no-color` keeps plain text readable.
Time windows are ISO 8601 UTC, `--start` / `--end`; without them a
search returns the most recent events and a query scans the whole
stream.

### Discovery

- Signals (saved filters) the server carries, `Logs`, `Spans`, `Errors`
  among the automatic ones: `seqcli signal list --json`
  ([signals](https://datalust.co/docs/signals)).
- The properties in play over a window:
  `seqcli query -q "select count(*) from stream group by @Level" --start=<iso> --json`.

### Logs

- Latest events matching a filter, newest first
  ([filter syntax](https://datalust.co/docs/the-seq-query-language)):
  `seqcli search -f "App = 'checkout'" -c 50 --start=<iso> --end=<iso> --json`.
  The default `-c` is 1 — always pass a count.
- Aggregates ([SQL queries](https://datalust.co/docs/sql-queries)):
  `seqcli query -q "select count(*) from stream where @Level = 'Error'" --start=<iso> --end=<iso> --json`
  returns `{"Columns": [...], "Rows": [[...]], "Statistics": {...}}`.
  A **`group by time(...)`** query returns a different shape (verified
  2026-09-04): `{"Columns": [...], "TimeColumnMetadata": {...},
  "Slices": [{"Time": "<iso>", "Rows": [[...]]}, ...], "Statistics":
  {...}}` — one slice per interval, empty intervals included with a
  zero row, and no top-level `Rows` at all. Read `Slices`, never
  `Rows`, whenever the query groups by time; it is also the cheapest
  way to find where a sparse window's data actually sits.
- Follow the stream live, server-side filter:
  `seqcli tail -f "@Level = 'Error'" --json` (runs
  until interrupted — always run it with a timeout in a mission).

### Traces

Spans are events too: a span carries `@sp` (span id), `@tr` (trace id)
and `@Start`; a log event emitted inside a span carries `@sp` and
`@tr` without `@Start` ([tracing](https://datalust.co/docs/getting-traces-into-seq)).
In filters the long names apply: `@SpanId`, `@TraceId`, `has(@Start)`.

- Spans over a window:
  `seqcli search -f "has(@Start) and has(@SpanId)" -c 50 --start=<iso> --end=<iso> --json`.
- One trace, spans and logs together:
  `seqcli search -f "@TraceId = '<trace id>'" -c 200 --json`.
- Span counts by service:
  `seqcli query -q "select count(*) from stream where has(@Start) group by @Resource.service.name" --start=<iso> --json`
  (the sample data carries no resource, the column is then `null`).
- Span duration is the built-in `@Elapsed` (`@Timestamp - @Start`), in
  Seq's native **100 ns ticks**
  ([built-in properties](https://datalust.co/docs/built-in-properties-and-functions)) —
  divide by 10 000 for milliseconds. It filters and aggregates
  (verified 2026-09-04):
  `seqcli query -q "select count(*), percentile(@Elapsed, 50), percentile(@Elapsed, 99), max(@Elapsed) from stream where has(@Start) group by RequestMethod" --start=<iso> --end=<iso> --json`
  for the per-operation quantiles, and
  `seqcli search -f "has(@Start) and @Elapsed > 500ms" -c 20 --start=<iso> --end=<iso> --json`
  for the exemplar above a threshold. Duration literals (`500ms`,
  `1s`) work in both `search -f` and `query -q`; a raw number is ticks,
  so a p99 read from `percentile(@Elapsed, 99)` can be pasted straight
  back into a filter.

Ingestion: an OpenTelemetry SDK exports to Seq with
`OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` and the traces endpoint
`<server url>/ingest/otlp/v1/traces`, logs at `/ingest/otlp/v1/logs`
([OTLP](https://datalust.co/docs/tracing-from-opentelemetry-sdks)).

### Metrics

Not verified (2026-09-04). Seq documents an OTLP metrics endpoint,
`<server url>/ingest/otlp/v1/metrics`
([metrics from OpenTelemetry](https://datalust.co/docs/metrics-from-opentelemetry-sdks)),
and the query language aggregates over events; how a metric point is
stored and which property names it carries were not exercised — a
mission that needs metrics must discover the shape first
(`seqcli search -f "has(@Metric)"` is a guess, not a verified filter)
and record what it found here.

### Profiles

Not served: Seq stores no profiling data. A mission that needs
profiles says so and moves on.

### Concurrency

`seqcli` is a plain HTTP client and takes concurrency well: an
observation run issued up to 14 `search` and `query` invocations
side by side from one shell, all exiting 0 with complete output
(2026-09-04). No limit is documented — run the discovery and the
exemplar fetches concurrently.

### Output traps

- `seqcli node health` prints `Unreachable` and exits **0** when the
  server does not answer: read the JSON `status` field, never the exit
  code.
- `seqcli sample ingest` is a continuous simulator, it never returns
  on its own — never run it without a timeout; it is a demo-data
  generator, not a query.
- Timestamps (`@t`) are in the server's local offset; convert to UTC
  before comparing with a window.

## Planning notes

- Seq is a log-and-trace store: metrics are documented but unverified
  here, profiles absent — plan a mission on logs and traces, and say
  which signals it could not cover.
- Structured properties are the way in: filter on the properties the
  service actually emits (`@Level`, `@Exception`, the service's own
  names), discovered with a group-by query before any search.
- The built-in sample data (`seqcli sample ingest`) is the baseline
  used to verify this file; a real service's events differ in shape —
  discover before asserting.
- No span-derived RED metrics exist here: Seq stores events, it derives
  nothing from spans. A per-operation table is built from the root
  spans themselves — `@Elapsed` percentiles grouped by the operation's
  own properties — and the child spans give the downstream call count
  per request. Traces are one flat parent/child tree per request
  (`@ps` is the parent span id); plan the operation grouping on the
  properties the service emits, since `@SpanKind` may be `Internal`
  throughout (verified 2026-09-04).

## Configuration display

### Display

- The instance: `seqcli config get -k connection.serverUrl` (or
  `SEQCLI_CONNECTION_SERVERURL` when set — say which answered).
- The client: `seqcli version`.
- Never echo `connection.apiKey`, `SEQCLI_CONNECTION_APIKEY`, or any
  `-a` value; `seqcli config list` prints the key's field, do not run
  it for the display.

### Connection proof

`seqcli node health --json` — connected when the JSON carries
`"status":"healthy"`. `Unreachable` (still exit **0**) means the
server does not answer at the configured URL; an authentication error
means the instance needs an API key. Either way the fix is the user's,
in `## Setup`: point `connection.serverUrl` at the instance, put the
key into `connection.apiKey` — never done for them.

### Change-request phrasing

- "switch to seq", "use Seq", "point the runs at my Seq"

## What to persist

### What stack_config holds

Nothing: `seqcli`'s own configuration names the instance and holds
the key (`## Setup`), like a CLI context. The frontmatter declares an
empty field list, and `stack_config.seq` stays `{}` — not configured,
the correct final state.

### Where each value comes from

Not applicable — the server URL lives in `SeqCli.json`, set by the
user with `seqcli config -k connection.serverUrl -v <url>`.

### What to ask the user

Nothing to persist. When the connection proof fails, ask them to run
the `## Setup` commands — the URL their Seq answers on (the UI's
address, the same port serves the API; `http://localhost:5341` for the
package's `docker-compose/seq`), and the API key by name only.
