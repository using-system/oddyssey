# Dynatrace — `dtctl` (+ Monaco, `dtcli`)

Official docs: https://docs.dynatrace.com/, https://developer.dynatrace.com/,
https://github.com/dynatrace-oss/dtctl
`docs.dynatrace.com` and `developer.dynatrace.com` pages are HTML-only (no
raw-markdown mirror found); the `dtctl` docs live as plain `.md` files in
its GitHub repo and are fetchable raw via
`raw.githubusercontent.com/dynatrace-oss/dtctl/main/docs/<file>.md`.

The user-mentioned name **`dtctl` is real** — it is an open-source,
kubectl-styled CLI published by Dynatrace itself under the `dynatrace-oss`
GitHub org, distinct from two older, narrower tools: `dt-cli` (PyPI package
`dt-cli`, Python module name `dtcli`) for signing/building/uploading
Extensions Framework 2.0 packages, and Monaco, a separate configuration-as-code
tool. There is no CLI that runs "raw DQL" other than `dtctl query`; absent
that, DQL is executed over the Grail Query REST API with `curl`.

## CLI binary

- **Binary**: `dtctl`
- **Detect**: `command -v dtctl`
- **Install**: `brew install dynatrace-oss/tap/dtctl`, or the install.sh
  script, or a release binary — see the install row below
  (INSTALLATION.md link). Raw DQL over curl is the documented no-CLI
  fallback for queries, but the skills below still require the binary.

## Setup

| Topic | Link | What to do with it |
| --- | --- | --- |
| `dtctl` install | [dtctl INSTALLATION.md](https://github.com/dynatrace-oss/dtctl/blob/main/docs/INSTALLATION.md) | `brew install dynatrace-oss/tap/dtctl`, or `curl -fsSL https://raw.githubusercontent.com/dynatrace-oss/dtctl/main/install.sh \| sh` (macOS/Linux), or download a release binary. Requires Go 1.24+ only if building from source. |
| `dtctl` auth & first query | [dtctl QUICK_START.md](https://github.com/dynatrace-oss/dtctl/blob/main/docs/QUICK_START.md) | OAuth (recommended): `dtctl auth login --context my-env --environment "https://<envid>.apps.dynatrace.com"`. Token-based: `dtctl config set-context ...` + `dtctl config set-credentials my-token --token "dt0s16.…"`. Verify with `dtctl auth whoami` — it doubles as the preflight's context display (identity + environment) and its cheapest connection probe. |
| `dtctl` required scopes | [dtctl TOKEN_SCOPES.md](https://github.com/dynatrace-oss/dtctl/blob/main/docs/TOKEN_SCOPES.md) | Per-operation scope list — `storage:logs:read`, `storage:metrics:read`, `storage:spans:read`, `storage:events:read`, plus `automation:workflows:*`, `document:documents:*`, `settings:*` for non-telemetry resources. Use to scope a token/OAuth client to least privilege. |
| Dynatrace Hub listing | [dtctl on Dynatrace Hub](https://www.dynatrace.com/hub/detail/dtctl/) | Dynatrace's own catalog entry for `dtctl`, plus the [launch blog post](https://www.dynatrace.com/news/blog/dtctl-the-dynatrace-observability-cli-thats-built-for-ai-agents-and-humans/) — use as corroboration that this is a Dynatrace-endorsed OSS tool, not a third-party guess. |
| API tokens vs. OAuth clients vs. platform tokens | [Dynatrace API — Tokens and authentication](https://docs.dynatrace.com/docs/dynatrace-api/basics/dynatrace-api-authentication) | Three credential kinds share a `dt0sNN.<public>.<secret>` shape: `dt0s01` classic API tokens (`Authorization: Api-Token …`), `dt0s02` OAuth2 clients, `dt0s16` platform tokens. Classic Environment APIs (e.g. Metrics API v2) take an API token; Grail/DQL and most platform APIs take an OAuth bearer token instead. |
| Create/manage an OAuth client | [OAuth clients](https://docs.dynatrace.com/docs/manage/identity-access-management/access-tokens-and-oauth-clients/oauth-clients) | Create a client in the account management UI, pick scopes up front (a minted token can only request a subset of them later) — needed before the client-credentials curl flow below will work. |
| Get an OAuth bearer token from the CLI (curl) | [Access platform APIs from outside](https://developer.dynatrace.com/develop/guides/access-platform-apis-from-outside/) | `curl --request POST 'https://sso.dynatrace.com/sso/oauth2/token' --data-urlencode 'grant_type=client_credentials' --data-urlencode 'client_id=…' --data-urlencode 'client_secret=…' --data-urlencode 'scope=storage:logs:read storage:metrics:read storage:spans:read'` → `access_token` (valid 300s), sent as `Authorization: Bearer …` on subsequent calls. |
| Extensions packaging CLI (`dt-cli`/`dtcli`) | [dynatrace-oss/dt-cli](https://github.com/dynatrace-oss/dt-cli) | For building/signing/uploading Extension Framework 2.0 packages only — not a query tool. Installed via `pip install dt-cli`. |
| Configuration as code (Monaco) | [Configuration as Code via Monaco](https://docs.dynatrace.com/docs/deliver/configuration-as-code/monaco), [Monaco CLI commands](https://docs.dynatrace.com/docs/deliver/configuration-as-code/monaco/monaco-cli-commands) | `monaco deploy`/`download`/`delete` manage dashboards, Settings 2.0 objects, workflows, etc. as YAML — it "can only manage configuration"; it has no command to query logs, metrics, or traces. |

## Query by signal

| Signal | How | Link | Notes |
| --- | --- | --- | --- |
| Logs | `dtctl query 'fetch logs \| filter status=="ERROR" \| limit 100'` | [dtctl QUICK_START.md](https://github.com/dynatrace-oss/dtctl/blob/main/docs/QUICK_START.md), [DQL data source commands](https://docs.dynatrace.com/docs/platform/grail/dynatrace-query-language/commands/data-source-commands) | `-o table\|json\|yaml\|csv`; pipe a `.dql` file with `-f queries/errors.dql`. Needs `storage:logs:read` (+ `storage:buckets:read`). No `dtctl` → curl POST to `/platform/storage/query/v1/query:execute` with the same DQL string as `{"query": "..."}`, `Authorization: Bearer <oauth token>`. |
| Logs / spans (discovery: fields) | `dtctl query 'fetch logs \| fieldsSummary k8s.namespace.name, log.source'` | [DQL aggregation commands](https://docs.dynatrace.com/docs/platform/grail/dynatrace-query-language/commands/aggregation-commands), [DQL commands](https://docs.dynatrace.com/docs/platform/grail/dynatrace-query-language/commands) | Grail is schema-on-read, so discovery is a query, not a catalog call: `fieldsSummary <field>, …` "calculates the cardinality of field values that the specified fields have", returning `field`, `rawCount`, `count`, and a `values` array of value/occurrence pairs — the way to learn which services/namespaces a bucket actually carries. Companions on the same page set: `fieldsSnapshot` (fields present in a data object's records) and `describe` (on-read schema of a data object). Works the same on `fetch spans`. |
| Metrics (discovery: metric keys) | `dtctl query 'load "/dt/platform/metrics.metadata" \| filter contains(metric.key, "host.cpu") \| fields metric.key, name, unit, dimensions'` | [DQL metric commands](https://docs.dynatrace.com/docs/platform/grail/dynatrace-query-language/commands/metric-commands), [Metrics API — GET metrics](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/metric-v2/get-all-metrics) | `load "/dt/platform/metrics.metadata"` exposes the list of metrics available in the environment, one row per metric with `metric.key`, `name`, `description`, `kind`, `unit`, `dimensions`, `metric.type`, `updated` — run it before `timeseries` instead of guessing a metric key. Classic-API equivalent, no OAuth needed: `curl -H 'Authorization: Api-Token dt0s01.…' 'https://<envid>.live.dynatrace.com/api/v2/metrics?fields=unit,aggregationTypes&metricSelector=builtin:*'` (scope `metrics.read`, `pageSize` max 500). |
| Metrics (DQL/Grail) | `dtctl query 'timeseries avg(builtin:host.cpu.usage), by:{dt.entity.host}'` | [DQL metric commands](https://docs.dynatrace.com/docs/platform/grail/dynatrace-query-language/commands/metric-commands), [DQL timeseries examples](https://docs.dynatrace.com/docs/analyze-explore-automate/metrics/dql-examples) | Metrics use the `timeseries` command, **not** `fetch metrics` — DQL's `fetch` covers logs/spans/bizevents/entities/events/problems but metrics are a dedicated command. Needs `storage:metrics:read`. |
| Metrics (classic Environment API, no OAuth needed) | `curl -H 'Authorization: Api-Token dt0s01.…' 'https://<envid>.live.dynatrace.com/api/v2/metrics/query?metricSelector=builtin:host.cpu.usage:avg&from=now-1h'` | [Metrics API v2](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/metric-v2), [GET data points](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/metric-v2/get-data-points) | Older, non-Grail API that predates DQL; simpler auth (plain API token, no OAuth dance) if a full DQL/Grail setup isn't wanted. `dtctl` does not wrap this API — it only speaks DQL. |
| Traces / spans | `dtctl query 'fetch spans \| filter dt.entity.service=="SERVICE-XYZ" \| limit 50'` | [DQL data source commands](https://docs.dynatrace.com/docs/platform/grail/dynatrace-query-language/commands/data-source-commands), [Advanced Tracing Analytics powered by Grail](https://docs.dynatrace.com/docs/observe/application-observability/distributed-tracing/advanced-tracing-analytics) | `fetch spans` exposes every span attribute stored in Grail (same DQL surface as logs). Needs `storage:spans:read`. No CLI/API exists to download a single trace's full waterfall outside the web UI — DQL span queries are the terminal-accessible path. |
| Profiles | No `dtctl` or DQL surface — Dynatrace does collect method-level CPU and memory profiling, but **Profiling & Optimization** is a web-UI app with no documented query API. | [Profiling and optimization](https://docs.dynatrace.com/docs/observe/application-observability/profiling-and-optimization), [CPU profiling](https://docs.dynatrace.com/docs/observe/applications-and-microservices/profiling-and-optimization/cpu-profiling) | Continuous CPU profiling "highlights the biggest CPU consumers in your environment and allows you to drill down to the method level of a CPU problem"; memory allocation analysis hangs off the same app. Both are reached by going to **Profiling & Optimization** in the UI and picking an analysis — the fetched pages document no REST endpoint, no DQL data object, and no `dtctl` command for stack traces, and `dtctl`'s scope list has no profiling scope next to `storage:{logs,metrics,spans,events}:read`. Treat profiles as unreachable from a terminal on this backend. |
| Raw DQL (curl, no `dtctl`) | `curl -X POST 'https://<envid>.apps.dynatrace.com/platform/storage/query/v1/query:execute' -H 'Authorization: Bearer …' -H 'Content-Type: application/json' -d '{"query":"fetch logs \| limit 10"}'` then poll `GET .../query:poll?request-token=…` | [Grail service](https://developer.dynatrace.com/develop/platform-services/services/grail-service/), [Query Grail data](https://docs.dynatrace.com/docs/platform/grail/dynatrace-grail/query-data) | Execution is async: `query:execute` returns a `request-token`; poll `query:poll` with it until the query finishes. Final results are only guaranteed available for **one minute** after completion — poll faster than that. This is the documented API alternative for any signal when `dtctl` isn't installed. |

Concurrency — **not verified**: the observe-run agent runs its
discoveries and its trace fetches backgrounded in one shell call, and
`dtctl query` submits independent DQL executions against Grail
sharing one context, so nothing in its design objects to it — but no
Dynatrace environment was available to prove it (2026-09-04). Until a
live check lands here, treat a concurrent failure as a possible CLI
limit before a backend fault: rerun the failed commands serially
once, and record which shape answered.

## Planning notes

- `dtctl` is real, Dynatrace-published OSS (`dynatrace-oss/dtctl`, listed on
  Dynatrace Hub) but its own README describes it as under "active
  development" with possible bugs, and `dtctl serve http` is explicitly
  experimental (verified 2026-08). Treat it as a supported convenience
  layer over the platform API, not a versioned GA product with an SLA.
- Two auth mechanisms don't mix: the classic Environment API (Metrics API
  v2) takes a plain `Api-Token` (`dt0s01…`) header; Grail/DQL access
  (`dtctl query`, `query:execute`) requires an OAuth bearer token
  (`dt0s02` client-credentials or `dt0s16` platform token) with
  `storage:*:read` scopes plus bucket/table permissions on the target data.
  A token minted for one won't work for the other.
- Coverage gap: profiles are UI-only. Dynatrace's CPU and memory profiling
  is real and method-level, but it is delivered through the Profiling &
  Optimization app; no DQL data object, REST endpoint, or `dtctl` command
  for stack traces is documented, and `TOKEN_SCOPES.md` lists no profiling
  scope (verified 2026-08). Record it as a telemetry gap in the report
  rather than concluding the environment has no profiling.
- Coverage gap: there is no dedicated CLI or API to pull one trace's full
  waterfall/JSON outside the web UI — `fetch spans` via DQL is the closest
  terminal-accessible substitute, returning individual span rows rather
  than an assembled trace tree.
- Monaco and `dt-cli`/`dtcli` are easy to confuse with `dtctl` by name but
  solve different problems: Monaco only pushes/pulls *configuration*
  (dashboards, settings, workflows) and cannot query telemetry at all;
  `dt-cli` only packages/signs *extensions* — neither touches logs,
  metrics, or traces.

## Configuration display

### Display

The active `dtctl` context is the configuration: which environment the
DQL queries will run against.

- `dtctl auth whoami` — the authenticated identity and the environment
  URL (`https://<envid>.apps.dynatrace.com`) of the active context.
  Show the context name, the environment, and the identity; never the
  token value behind them.
- The setup section earlier in this file owns the CLI specifics (OAuth
  vs token contexts, how a context is created); this section owns only
  what to display.

`stack_config.dynatrace` is expected **empty** — the dtctl context
already names the environment. Present-and-empty (`{}`) or missing both
display as "nothing persisted — the dtctl context is the source".

Add any `invalid_ignored` dotted names as degradations: the stored
value was invalid and was dropped. `stack_config` has no defaults behind
it, so a dropped value reads as not persisted — nothing silently took
its place.

### Connection proof

`dtctl auth whoami`. It is both the context display and the cheapest
probe — one call that either returns the identity and environment
(connected) or fails. Failure = stop and guide `dtctl auth login` /
the token context setup; never run the login for the user.

### Change-request phrasing

- "change backend to dynatrace"

## What to persist

### What stack_config holds

**Nothing.** `stack_config.dynatrace` is expected to stay empty, and an
empty entry is the correct final state of a switch to `dynatrace`.

`dtctl` is context-bearing: the active context already names the
**environment** the DQL queries run against
(`https://<envid>.apps.dynatrace.com`) and the identity behind it.
Storing the environment id or URL here would only be a stale copy of
what `dtctl auth whoami` reports first-hand, and the context is what the
query uses either way.

### Where each value comes from

From the active dtctl context, read at use time:

- `dtctl auth whoami` — the authenticated identity and the environment
  URL of the active context. One call, and it is both the display and
  the connection proof.

Whether the context is an OAuth context or a token context, the
credential lives in dtctl's own configuration; name the mechanism if it
helps the user, never the value. The setup section earlier in this
file owns how a context is created.

### What to ask the user

**Nothing about targeting.** Do not ask for the environment id, the
environment URL, or any credential.

If the user has several dtctl contexts and the active one is not the
environment they mean, the fix is a dtctl context switch, not a value in
this configuration — say so and let them run it, then re-verify.

Leave `stack_config.dynatrace` alone.
