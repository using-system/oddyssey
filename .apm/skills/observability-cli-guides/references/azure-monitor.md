# Azure Monitor — `az` (Azure CLI)

Azure Monitor is queried from the terminal with `az`: KQL against an
Application Insights **component** (`requests`, `dependencies`,
`customMetrics`, `traces`, `exceptions` - the APM signals, through
`az monitor app-insights query`) and against a Log Analytics
**workspace** (the platform's `*_CL` tables, through
`az monitor log-analytics query`), and the platform metrics of a
resource through `az monitor metrics list`. This skill ships, in its
`scripts/`, the scripts a run invokes so that it composes no `az`
command and no KQL by hand; the preflight and the switch read the four
configuration sections, the agents the rest. Official docs:
[az monitor](https://learn.microsoft.com/en-us/cli/azure/monitor),
[Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/).
CLI reference pages (`/cli/azure/...`) return raw markdown when
`?view=azure-cli-latest&accept=text/markdown` is appended to the URL;
the conceptual pages do not.

Verified live 2026-09-11, azure-cli 2.89.1 with the application-insights 1.2.3 and log-analytics 1.0.0b1 extensions, against a live subscription carrying real data - an Application Insights component fed by an OpenTelemetry Collector (a service on Azure Container Apps driven continuously, about 1 700 requests per 15 minutes with failures, with requests, dependencies, traces and customMetrics; exceptions present as an empty table only) and its Log Analytics workspace (ContainerAppConsoleLogs_CL, ContainerAppSystemLogs_CL) and the container apps' platform metrics; every script invocation below run over 15-minute windows between 10:35 and 11:10 UTC (24-hour windows where the bullet says so); the connection proof's wrong-value shapes (an unknown appId, a resource name) exercised, its identity-failure and rights-failure shapes not (marked below); the first-use extension install not re-observed (both extensions present).

## CLI binary

- **Binary**: `az`
- **Detect**: `command -v az`
- **Install**: `brew install azure-cli` (macOS) or the official installer
  per platform: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
  - the `log-analytics` and `application-insights` extensions auto-install
  on first use (from the documentation, not run 2026-09-11 - both were
  installed).

## Setup

| Topic | Link | What to do with it |
| --- | --- | --- |
| Sign in | [authenticate-azure-cli](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli) | Interactive `az login` (browser, picks a default subscription), managed identity, or service principal. Since September 2025 a user identity needs MFA at `az login`; service principals and managed identities are unaffected - plan automation on one of those. |
| Service principal login | [authenticate-azure-cli-service-principal](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-service-principal) | `az login --service-principal --username <APP_ID> --password <CLIENT_SECRET> --tenant <TENANT_ID>` (or `--certificate <path>`); the secret is the user's, referred to by name, never written here. |
| Default subscription | [find or change the current subscription](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli#find-or-change-your-current-subscription) | `az account set --subscription "<id-or-name>"`; every command runs against it unless `--subscription` says otherwise. |
| Context and connection probe | [az account show](https://learn.microsoft.com/en-us/cli/azure/account#az-account-show) | Displays the active subscription and tenant; fails with a "Please run 'az login'" message when not authenticated. Run through `scripts/azure-monitor-context.py check` (below). |
| Diagnostic settings | [az monitor diagnostic-settings](https://learn.microsoft.com/en-us/cli/azure/monitor/diagnostic-settings) | Routes a resource's platform logs to the workspace - required before a resource's logs are queryable there. |
| Workspace management | [az monitor log-analytics workspace](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics/workspace) | `show -g <resource_group> -n <name> --query customerId -o tsv` turns a workspace name into the GUID `--workspace` takes. |

## Query by signal

The signals are read with the scripts this skill ships in `scripts/` -
never with `az` commands or KQL composed by hand. The shared module
`scripts/azure_monitor_az.py` carries, in code, every transport trap
verified 2026-09-11: the two output shapes (the component's typed
`tables[0]`, the workspace's flat stringified row list - one parser each);
`customDimensions` double-encoded as a JSON string; the extension and
preview `WARNING:` noise on stderr; the exit codes (0; **3 only for a
resource that does not exist**; **2 when az could not parse the command**;
**1 for everything else**, the `ERROR:` line being the diagnosis, never the
"unexpected error ... Here is the traceback" banner) with the `ERROR:` line
classified - the component's tokenless `BadArgumentError` (any unsupported
function or alias - `first`, `last`, `percentileif` -, an unknown column,
a bin converted inside the same `summarize`), the workspace's `Inner error`
JSON (which does name the `SEM0100` semantic error), a value that is not an
appId GUID, an identity that must log in again, missing rights, an unknown
platform metric (the valid names are listed), an unsupported dimension;
and the explicit window on every query (`--start-time`/`--end-time` on the
component, `--timespan <start>/<end>` on the workspace - the default
`--offset` of 1h silently bounds an older window to 0 rows). Each
invocation below is copy-pasteable - `<Skills>` is the `skills` line the
preflight handoff carries (the `package-layout` skill's
`scripts/layout.py`) - and states the script's **whole** flag surface:
`--help` has nothing to add and the files have nothing to read. A run that lacks a shape of the
work records it in its report's `## 8. Stack friction`, never a wrapper.

Common to every script: the targeting values come from
`stack_config.azure-monitor` and are passed as flags - `--app
<app_insights_app>` (the component's appId GUID, never with `-g` beside
it, never with `--subscription`: the data plane needs neither),
`--workspace <workspace>` (the Log Analytics customer ID GUID),
`--resource-group <resource_group>` and `--subscription <subscription>`
where an ARM read takes them; a **window** is `--from <RFC3339 UTC> --to
<RFC3339 UTC>` or `--since <duration>` (`30m`, `2h`); a **service** is
`--service <cloud_RoleName>` (repeatable, none = every service); `--json`
prints the same result as one object carrying the keys the `Output` line
names plus `commands` and `failed`; exit 0 means every query ran (an empty
answer is a result), 1 that a query failed - **the failure is in the
output**, under `FAILED` with its classification -, 2 a usage error.
**Every subcommand ends by printing the `az` commands it ran** - `queries
run (record these):`, the header saying how many calls when exact
repeats were folded - with the targeting values and a resource id
**replaced by their field names in angle brackets** (`--app
<app_insights_app>`, `--workspace <workspace>`, `--resource <resource>`),
so the lines go into a committed report as printed. The scripts run their
independent calls **concurrently** against one login - verified
2026-09-11, eight `query` calls side by side in 1.4 s, all complete. The
commands behind the scripts are
[az monitor app-insights query](https://learn.microsoft.com/en-us/cli/azure/monitor/app-insights#az-monitor-app-insights-query),
[az monitor log-analytics query](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics#az-monitor-log-analytics-query),
[az monitor metrics list](https://learn.microsoft.com/en-us/cli/azure/monitor/metrics#az-monitor-metrics-list),
[az monitor metrics list-definitions](https://learn.microsoft.com/en-us/cli/azure/monitor/metrics#az-monitor-metrics-list-definitions),
[az resource list](https://learn.microsoft.com/en-us/cli/azure/resource#az-resource-list)
and [az account show](https://learn.microsoft.com/en-us/cli/azure/account#az-account-show);
the KQL in them is the
[Application Insights data model](https://learn.microsoft.com/en-us/azure/azure-monitor/app/data-model-complete)
with [percentile](https://learn.microsoft.com/en-us/kusto/query/percentiles-aggregation-function),
[arg_max](https://learn.microsoft.com/en-us/kusto/query/arg-max-aggregation-function),
[prev](https://learn.microsoft.com/en-us/kusto/query/prev-function),
[join](https://learn.microsoft.com/en-us/kusto/query/join-operator),
[union](https://learn.microsoft.com/en-us/kusto/query/union-operator),
[extract](https://learn.microsoft.com/en-us/kusto/query/extract-function)
and [getschema](https://learn.microsoft.com/en-us/kusto/query/getschema-operator).

### First, in one call: what the window holds - and where the environment is read from

```bash
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-discover.py --app <app_insights_app> --workspace <workspace> --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-discover.py --app <app_insights_app> --service <svc> --since 30m --json
```

Whole surface: `--app`, `--workspace` (one of the two at least),
`--service`, a window, `--console-table` (the workspace table holding a
container platform's console lines, default `ContainerAppConsoleLogs_CL`),
`--container-column` (its container-name column, default
`ContainerName_s`), `--top` (operations listed per service, default 15),
`--json`. **This is the first read of a window**: it carries the
deployment-environment detection, so a run composes nothing for it.
Output: per service (`cloud_RoleName`) `tables` (rows per `itemType`:
`request`, `dependency`, `customMetric`, `trace`, `exception`),
`environment` (read off the resource attributes the rows carry in
`customDimensions` - `deployment.environment.name`, falling back to
`deployment.environment` - with `environment_read_from` naming the key
that answered, or `nothing`), `resource` (one row per `service.version` and
`service.instance.id`), `operations` (the request names with `n` and
`failed`), `metrics` (the `customMetrics` names with `rows`, `points` =
`sum(valueCount)` and `aggregated` when a row carries several points),
`severities` (the `traces` table by level), `exceptions` (by type);
`workspace.cl_tables` (the `*_CL` tables with rows in the window) and
`workspace.containers` (of the console table); `profiles: not served`;
`failed` (exit 1 when non-empty). A side not given is a **stated gap,
never worked around**: without `--app` the output says the run is
logs-only and distributed tracing a telemetry gap; without `--workspace`
that the platform's console and system tables are not read. Verified 2026-09-11
(both sides; component only; workspace only): the environment came back
`dev` from `deployment.environment.name` on every row - the
`deployment.environment` fallback is unverified 2026-09-11 (no row carries
the old key). Runs its eight queries side by side.

### Traces

Spans live in `requests` (incoming) and `dependencies` (outgoing), never in
`traces` (the log table); a trace is every row sharing an `operation_Id`,
a span's parent is `operation_ParentId`, a log line or an exception hangs
off the span it names there. This backend derives no per-operation series
from the spans: the per-operation table is built from `requests`, which
these scripts do.

```bash
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-traces.py operations --app <app_insights_app> --service <svc> --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-traces.py dependencies --app <app_insights_app> --service <svc> --since 30m
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-traces.py exemplars --app <app_insights_app> --service <svc> --slow 3 --failed 3 --since 30m
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-traces.py trace <operation_Id> --app <app_insights_app> --from <start> --to <end>
```

Whole surface: every subcommand takes `--app`, a window (`trace` defaults
to the last 24h when none is given), `--json`; `operations`,
`dependencies` and `exemplars` take `--service`; `operations` adds `--top`
(rows, default 20) and `--bin <duration>` (adds the request count,
failures and p95 per time bucket); `exemplars` adds `--operation <request
name>` (repeatable), `--slow N` (the slowest requests, default 3),
`--failed N` (the newest failed requests, default 3); `trace` takes the
`operation_Id`.

- `operations` - Output: one row per service and request `name` - `n`,
  `failed` (`success == false`), `failed_codes` (`resultCode` counts of
  the failures), `p50`, `p95`, `p99`, `max` of `duration` in ms; `bins`
  with `--bin` (one row per bucket over every service given - name one
  `--service` for a per-service series). The percentiles are one `summarize ... by name` - there
  is no `percentileif`, and none is needed. Verified 2026-09-11: five
  operations, `--bin 5m` three buckets.
- `dependencies` - Output: `per_operation` (each dependency `type`/`name`
  under the request operation sharing its `operation_Id` - a join done
  here, because a dependency's `operation_Name` is empty on an OTel
  export - with `n`, `failed`, the percentiles) and `all` (every
  dependency of the window by caller, `type`, `target`, `name`: what the
  join leaves out - a client span whose request is outside the window).
  Verified 2026-09-11: seven joined rows (the load generator's client
  spans and the service's own outgoing calls), five in `all`.
- `exemplars` - Output: `slow` and `failed_requests`, each request with
  `timestamp`, `name`, `duration`, `resultCode`, `operation_Id`, `id`
  and, from one union over the picked ids, its `dependencies`,
  `exceptions` and `logs` (the `traces` rows of warning level and above).
  Verified 2026-09-11: the slowest carried its `payment.authorize`
  dependency, a failed one its failed `storage.delete` and the warning
  line explaining it.
- `trace` - Output: `summary` (`root`, `duration_ms`, `spans`,
  `failed_spans`, `logs`, `exceptions`, `services`) and `nodes`
  (depth-first: `request`/`dependency` spans with `duration`, `success`,
  `resultCode`, `type`, `target`; `trace` lines with their severity;
  `exception` rows with `type` and `outerMessage`). The root is the span
  without a parent in the set - the caller's client span when the caller
  is instrumented too. Verified 2026-09-11 (a three-span, two-log trace
  across two services); an unknown id prints `(no rows ...)` with exit 0.

### Metrics

Two sources: the component's `customMetrics` (the service's own OTel
exports: one row per export and series, `value`/`valueCount`/`valueSum`/
`valueMin`/`valueMax`, the attributes and the resource attributes in
`customDimensions`) and the platform metrics of a resource
(`az monitor metrics list`). The component derives no metric from its
spans; a per-operation table comes from `azure-monitor-traces.py operations` above.

```bash
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-metrics.py list --app <app_insights_app> --service <svc> --since 30m
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-metrics.py query <name> --app <app_insights_app> --service <svc> --by <dimension key> --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-metrics.py query <name> --app <app_insights_app> --as gauge --since 30m --json
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-metrics.py resources --resource-group <resource_group> --subscription <subscription>
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-metrics.py definitions --resource <resource id>
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-metrics.py platform --resource <resource id> --metric Requests RestartCount --aggregation Total --interval PT1M --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-metrics.py platform --resource <resource id> --metric Requests --dimension statusCodeCategory --since 30m
```

Whole surface: `list` - `--app`, `--service`, a window, `--json`.
`query <name>` - `--app`, `--service`, `--by <customDimensions key>`
(repeatable), `--bin <duration>` (one row per time bucket; ignored by the
cumulative reading, which is an edge over the whole window), `--as
auto|delta|cumulative|gauge|histogram` (default `auto`), a window,
`--json`. `platform` - `--resource` (a resource id, or a name with
`--resource-group` and `--resource-type`), `--subscription`, `--metric`
(repeatable, or several values), `--aggregation` (`Average`, `Count`,
`Maximum`, `Minimum`, `Total` - several allowed; omitted, the metric's
primary one), `--interval` (ISO 8601, default `PT1M`), `--dimension`
(repeatable, splits the series) **or** `--filter` (an OData dimension
filter, `"statusCodeCategory eq '5xx'"` - the two are mutually exclusive
on az, and the pair is a usage error here), `--show` (points printed
per series, the newest, default 6), a window, `--json`. `definitions` -
`--resource`, `--resource-group`, `--resource-type`, `--subscription`,
`--json`. `resources` - `--resource-group`, `--resource-type` (default
`Microsoft.App/containerApps`), `--subscription`, `--json`.

- `list` - Output: `metrics`, one row per service and `name` with `rows`,
  `points` (`sum(valueCount)`), `aggregated` (a row carries several
  points: a histogram-shaped export) and `dimensions` (the
  `customDimensions` keys beyond the resource's own - the `--by` values
  `query` takes). Verified 2026-09-11: seven names, the http.* ones with
  their route and status-code keys.
- `query <name>` - **the temporality probe runs first**: the rows are
  ordered per series (the whole `customDimensions` set) and the pushes
  that rose and fell against the previous row are counted with `prev()`;
  `increases` with no `decrease` is a **cumulative** pipeline and the
  window is read as the **edge delta per series** (`arg_max` minus
  `arg_min` of `value`, the columns being `latest, value, earliest,
  value1`, qualified by `service.instance.id` so a restart never reads as
  a drop); any `decrease` is a **delta** pipeline (each row one export's
  increment) and the window is `sum(value)`; a flat series is left
  `undetermined` with both readings printed; rows carrying several points
  are a **histogram** (`points`, `total`, `avg`, `vmin`, `vmax` in the
  metric's unit). **A gauge is never detected and must be told** (`--as
  gauge`: `avg`, `vmin`, `vmax`, `latest`). Output: `temporality`
  (`verdict`, `why`, `pushes`, `increases`, `decreases`, `series`, `vmax`)
  and `readings` keyed by the reading taken. Verified 2026-09-11 on the
  collector's delta pipeline: a counter `--by product.id` (49 decreases
  over 150 pushes, `delta`, ten rows), a histogram `--by http.route --by
  http.response.status_code` (eight rows), an UpDownCounter `--as gauge`,
  `--as cumulative` forced on the delta series (the edge reading ran; a
  truly cumulative pipeline is **unverified 2026-09-11** - the verdict
  rule is the built-in reference's 2026-09-03 observation), an unknown
  name (`none`, exit 0).
- `resources` - Output: the resources of the group with `name`, `type`,
  `location`, `id` - the id `platform --resource` takes, and a real
  identifier (the subscription GUID, the group, the resource's name):
  for that flag only, never for a report - the commands the scripts
  print mask it as `<resource>`. `definitions` -
  Output: `name`, `unit`, `primary` aggregation, `supported` aggregations,
  `dimensions` per metric: the `--metric`, `--aggregation` and
  `--dimension` values `platform` accepts. Verified 2026-09-11 (two
  container apps, 31 definitions).
- `platform` - Output: per metric `unit`, `series` (each with its
  `dimensions` - az lowercases the dimension name -, `points` carrying a
  value `of` the interval's points, `stats` per aggregation - `sum`,
  `avg`, `max`, `min`, `last` - and `data`) and `absence`: **an
  unpublished metric or a quiet one answers points without a value key**
  (`GpuUtilizationPercentage` on a container app: `0 of 3 points carry a
  value` - read it as "nothing happened" only when another metric over
  the same window returned values), **a `--dimension` split or a
  `--filter` that no series matches answers an empty `timeseries`**;
  both are stated, never printed as zeros. A metric that is published but idle (`RestartCount`) answers
  zeros, which are values. An unknown `--metric` fails with the valid
  names listed; a `--dimension` the metric lacks fails naming the
  supported ones - both classified, exit 1. Verified 2026-09-11 on all
  of the above, by id and by name with `--resource-group`/`--resource-type`,
  two metrics and two aggregations at once.

### Logs

Two log sources: the workspace's tables (the platform's console lines -
`ContainerAppConsoleLogs_CL` with `ContainerName_s`, `Stream_s` and `Log_s`
on Azure Container Apps; another host writes its own `*_CL` tables, and
**their columns are not interchangeable**: a column that worked on a
sibling table fails with `SEM0100`, so `schema` first) and the component's
`traces` table (the service's log records with `severityLevel`, `message`,
`operation_Id` and the instrumentation library in `customDimensions`).

```bash
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-logs.py tables --workspace <workspace> --since 24h
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-logs.py schema --workspace <workspace> --table ContainerAppSystemLogs_CL
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-logs.py count --workspace <workspace> --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-logs.py count --workspace <workspace> --container <svc container> --level-regex '^(\w+)' --since 30m
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-logs.py sample --workspace <workspace> --container <collector> --level error --since 30m --show 20
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-logs.py traces --app <app_insights_app> --service <svc> --min-severity 2 --since 30m
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-logs.py kql --workspace <workspace> "<KQL>" --since 24h
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-logs.py kql --app <app_insights_app> "<KQL>" --since 30m
```

Whole surface: `count` and `sample` - `--workspace`, `--table` (default
`ContainerAppConsoleLogs_CL`), `--container-column` (default
`ContainerName_s`), `--message-column` (default `Log_s`), `--stream-column`
(default `Stream_s`; `''` for a table without one), `--container`
(repeatable; none = every container), `--level-regex` (the KQL regex
whose first group is the level - default the collector's console line,
the second whitespace-separated field: `^\S+\s+(\w+)\s`; a line that
opens with the level takes `^(\w+)`; no double quote in it), a window,
`--json`; `sample` adds `--level` (case-insensitive equality on the
extracted level), `--contains <substring of the message>`, `--show` (the
newest lines, default 20). `schema` - `--workspace`, `--table`, a window
(default the last hour: `getschema` needs one), `--json`.
`tables` - `--workspace`, a window, `--json`. `traces` - `--app`,
`--service`, `--min-severity` (0 verbose, 1 information, 2 warning, 3
error, 4 critical; default 0), `--contains`, `--show` (default 20), a
window, `--json`. `kql` - exactly one of `--workspace` or `--app`, the KQL
string, `--show` (rows printed, default 50), a window, `--json`.

- `tables` - Output: the `*_CL` tables holding rows in the window, with
  `n` and `latest` (`union withsource=T *_CL`). Verified 2026-09-11 over
  24h: two tables.
- `schema` - Output: `columns` (`name:type`) of one table, from
  `getschema` - run it before `kql` names a column of a `*_CL` table.
  Verified 2026-09-11 (26 columns of the system-log table).
- `count` - Output: `rows` per `container`, extracted `level` (`(no
  match)` when the regex matches nothing - the level is then not where
  the regex looks: change `--level-regex`), `stream`, with `n` and
  `latest`. **Rule a collector's health on its level column, scoped to
  its container**, never on `has 'error'`: its `info` lines carry a JSON
  `"error"` field and match the term. Verified 2026-09-11: the default
  regex on the collector's container over 24h (`info` 18, `warn` 10);
  `^(\w+)` on the service's container (`INFO` on stdout and stderr, and
  a timestamp-first line shape on stderr that the regex reads as its
  year - a third line shape, told apart by `sample`).
- `sample` - Output: `matching` (the exact count of the filter) and
  `samples` (`time`, `container`, `level`, `stream`, `message`), newest
  first. Verified 2026-09-11: `--level info` on the collector over 24h,
  `--contains '" 502'` on the service's container.
- `traces` - Output: `severities` per service, `matching`, `samples`
  (`time`, `cloud_RoleName`, `severity`, `library`, `message`,
  `operation_Id`, `span_id` = `operation_ParentId`). Verified 2026-09-11
  (`--min-severity 2`: seven warnings, each naming its `operation_Id` -
  `azure-monitor-traces.py trace` prints its tree).
- `kql` - the one escape hatch for a query no script ships, run through
  the same transport (the explicit window, the error classified, the rows
  parsed); Output: `rows` and `total_rows`. Verified 2026-09-11 on both
  sides, and the two error shapes: a `SEM0100` from the workspace naming
  the column, a tokenless `BadArgumentError` from the component (`first=`
  alias), both exit 1.

### The landing of a driven run

```bash
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-context.py landing --app <app_insights_app> --identity <the run's user agent> --expect <request count> --from <start> --to <end>
```

Whole surface: `--app`, `--identity` (matched on
`customDimensions['user_agent.original']`), `--expect N`, a window,
`--dimension` (another `customDimensions` key to match on), `--service`,
`--every` (seconds between polls, default 20), `--cap` (the bound,
default `3m`), `--json`. Output: `polls` (elapsed seconds and the count
read in json at `tables[0].rows[0][0]`), `landed`, `count`; exit 0
landed, 1 the cap was reached with the last count in the output.
Verified 2026-09-11 (landed on the first poll; an identity that never
lands ran three polls to a 40 s cap, exit 1).

### Profiles

Not served on the CLI: Application Insights Profiler is enabled from `az`
(`az monitor app-insights component connect-webapp ... --enable-profiler`,
.NET web apps only) but read in the portal alone - no `az` subcommand and
no KQL table returns a profile
([View Profiler data](https://learn.microsoft.com/en-us/azure/azure-monitor/profiler/profiler-data)).
A mission records profiles as a telemetry gap and moves on.

### Residual traps, for a call still composed by hand

- `--app` takes the appId GUID **without** `-g` (with it: exit 3 even when
  both are right) or the resource name **with** `-g`; `component show`
  resolves a **name** only and demands `-g` - the persisted GUID is
  resolved to its name once with `az monitor app-insights component show
  --query "[?appId=='<app_insights_app>'].{name:name, rg:resourceGroup}"
  -o tsv` (subscription-wide on purpose: the component may sit outside
  `<resource_group>`). `show` also returns `instrumentationKey` and
  `connectionString`, both ingestion credentials: always project with
  `--query`, never echo the raw object.
- `| count` read under `-o tsv` prints **1** whatever the count (the
  number of result rows); read a count in `-o json` at
  `tables[0].rows[0][0]`, as the scripts do.
- `--query` on any `az` command is JMESPath, not KQL: `substring(...)`
  aborts with exit 2 before any call; filter with
  `value[0].timeseries[0].data[?average!=null]`.
- `dcount()` is a HyperLogLog estimate; `count()` over a column unique per
  row is exact - a spread between the two is not an anomaly.
- A bin is a grouping key: `bin(timestamp - datetime(<start>), 30s)` works
  in `by`, converting it in the same `summarize` is refused; convert in the
  `extend` after it.
- `requests | take 1` dumps `appName`, `iKey`, `_ResourceId` - resource
  identifiers a report must not carry: project the columns needed, as the
  scripts do.
- A KQL string inside a double-quoted shell argument under zsh:
  `$CD['x']` is a subscript and aborts before `az` runs - the scripts pass
  the query as one argument, no shell in between.

## Planning notes

- **The trace story is not the `traces` table**: spans are `requests` and
  `dependencies`, correlated on `operation_Id`; `traces` holds the log
  records (verified 2026-09-11).
- **A workspace alone cannot answer APM questions**: without a component,
  `requests`/`dependencies`/`customMetrics`/`traces`/`exceptions` are not
  there, and a run sees platform logs and platform metrics only -
  `discover` states it; the report records distributed tracing as a
  telemetry gap, never a fallback kept quiet.
- **Ingest latency is seconds to tens of seconds, never a fixed sleep**:
  wait with `azure-monitor-context.py landing` (`## Query by signal`,
  the landing subsection), which polls the run-identity count every
  ~20 s, capped; verified 2026-09-11 - a 10-minute window of
  the driven traffic answered its count on the first poll.
- **`customMetrics` temporality: probed before trusted** - `metrics.py
  query` does it on every read; the collector observed 2026-09-11
  converts to deltas (each row one export's increment; `sum(value)` is
  the count); a cumulative pipeline reads as running totals per series
  where `sum(value)` multiplies the total by the export count.
- **This backend derives no per-operation metrics from the spans**
  (verified 2026-09-11): the per-operation table is `traces.py
  operations`; a service publishing its own per-route series has them in
  `customMetrics` (`azure-monitor-metrics.py list` says).
- **Profiles are a coverage gap** on the CLI: portal-only, recorded in
  the report's telemetry gaps.
- The deployment environment is read where `discover`'s
  `environment_read_from` says - the resource attributes in
  `customDimensions` on an OTel-fed component (`dev` on 2026-09-11); a
  component fed otherwise may carry none - a run states that, it does
  not invent one.
- `exceptions` was empty over 7 days on the verification account
  (2026-09-11): its query ran and its shape on data (`type`,
  `outerMessage`, `problemId`) is the data model's, unverified on rows.
- The auth of automation is a service principal or a managed identity:
  the September 2025 MFA mandate applies to interactive `az login` only.
- Verification dates: every invocation above 2026-09-11 unless its
  bullet says otherwise.

## Configuration display

### Display

```bash
python3 <Skills>/observability-cli-guides/scripts/azure-monitor-context.py check --app <app_insights_app> --workspace <workspace>
```

Two sources, and every line says which one it came from - the CLI
identity and the persisted targeting values are different facts and a
mismatch between them is what this display exists to catch.

From `az account show` (the CLI's own context, printed by `check`): the
active subscription (name and id), the tenant id, the identity's type;
never `user.name` (a login name), never a token.

From `stack_config.azure-monitor` (persisted through
`odd_config_set`, read with `odd_config_get`), shown next to its field:

- `subscription` - the subscription the missions query, when pinned
  separately from the CLI's active one; say it plainly when it differs
  from the one `az account show` reports - the query targets the persisted
  one.
- `resource_group` - the resource group holding the workspace and the
  resources whose platform metrics are read; the component may sit in
  another one.
- `workspace` - the Log Analytics **customer ID** GUID (what `--workspace`
  takes), not the workspace's resource name.
- `app_insights_app` - the component's **appId** GUID (what `--app`
  takes), not its resource name.

A field the user did not persist reads "not persisted - the mission will
ask"; an empty `stack_config.azure-monitor` (`{}`) is all four
unset, a valid state. `app_insights_app` unset is the one exception to
that neutral wording - a **named degradation**:

> no Application Insights configured - `requests`/`dependencies`/
> `customMetrics`/`traces`/`exceptions` and the Profiler are unavailable,
> and the run will see Log Analytics tables and platform metrics only.
> Distributed tracing will be reported as a telemetry gap.

Any `invalid_ignored` dotted name is a degradation too: the stored value
was invalid and dropped, nothing took its place.

### Connection proof

The same `check` call, in **two parts** - `az` answering says nothing
about whether the persisted target exists, so a successful identity proof
alone is not a connected verdict when `app_insights_app` is persisted:

- **Identity**: `az account show` succeeding. It reads the local profile
  and never touches the network, so a stale token passes here and fails
  on the next part. Never run `az login` for the user: guide it.
- **Targeting**: `print 1` against the component with the appId alone
  (never `-g` beside it, never `--subscription`: the data plane needs
  neither), and with `--workspace` the same against the workspace; about
  a second each. Skipped - not failed - when `--app` is not given.

The exit code is the verdict, and the output carries the diagnosis:

- **0** - connected (both parts). Verified 2026-09-11.
- **3** - the persisted value does not resolve: an unknown appId
  (`ApplicationNotFoundError`, az's exit 3) or a value that is not an
  appId GUID (`The Application Insight is not found. Please check the app
  id again.` behind a traceback banner, az's exit 1 - typically the
  component's resource name); on the workspace, an unknown customer ID
  (`WorkspaceNotFoundError`) or a resource name in its place
  (`PathNotFoundError`), both az's exit 3 (verified 2026-09-11). A wrong value, never a "CLI not
  configured" error: route to `backend-configuration`'s `## Switch`
  **once** for a corrected value, then stop and report rather than
  bouncing. Both shapes verified 2026-09-11.
- **1** - an identity failure surfacing late (`AADSTS...`, or a "run `az
  login`" message: hand it to the identity guidance, do not route it to
  the switch, which cannot fix a login), a rights failure
  (`Forbidden`/`AuthorizationFailed`: authenticated but no query rights
  on this resource - re-persisting the same value will not fix it, name
  the missing access), or anything else (connection, proxy, throttling,
  service error - reported verbatim and retried, never rewritten as a
  targeting failure). The identity- and rights-failure shapes are
  **unverified 2026-09-11** (not reproducible without breaking the
  login); the classification rests on the messages the built-in
  reference recorded.
- **2** - az could not parse the command: a defect in the invocation,
  never a stored value.

`app_insights_app` unset is not a failed proof: it is the degradation
stated above, and the mission proceeds logs-only having said so.

**The landing poll of a driven run** is a query-time tool:
`azure-monitor-context.py landing`, stated with its whole surface under
`## Query by signal`.

### Change-request phrasing

- "switch to azure-monitor", "change backend to azure-monitor"
- "persist workspace <guid> for azure-monitor"
- "persist app insights <name-or-guid> for azure-monitor"
- "clear the workspace for azure-monitor"

## What to persist

### What stack_config holds

`az` is a **general-purpose** CLI: its context says who you are and which
subscription is active, nothing about where the telemetry lives. So
`stack_config.azure-monitor` holds the targeting the missions would
otherwise ask for on every run:

- `subscription` - the subscription the missions query, by name or id.
- `resource_group` - the resource group holding the workspace (and the
  resources whose platform metrics are read); the component may sit in
  another one.
- `workspace` - the Log Analytics workspace's **customer ID** GUID: what
  `--workspace` takes; not the resource name, which looks plausible in
  the same slot and fails.
- `app_insights_app` - the component's **appId** GUID: what `--app` takes
  with no `-g` beside it; not the resource name, not the instrumentation
  key.

The workspace and the component are two different things and the runs
need both: a workspace holds logs and platform metrics; distributed
tracing exists only inside a component. Persisting a workspace and no
component configures a run that reads logs and sees no trace - which is
why `app_insights_app` is asked for on every pass rather than waited for.
All four are identifiers; none is a secret - the credential behind `az`
stays in its own auth store.

### Where each value comes from

- `subscription` - `az account show` (the active subscription's name and
  id); persist it anyway, "active" is machine state that changes under
  you.
- `resource_group` - the group each workspace sits in:
  `az monitor log-analytics workspace list --query "[].{name:name, rg:resourceGroup}" -o table`
  ([workspace list](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics/workspace#az-monitor-log-analytics-workspace-list)).
- `workspace` - `az monitor log-analytics workspace show -g <resource_group> -n <name> --query customerId -o tsv`
  turns a workspace name into the GUID to store.
- `app_insights_app` - `az monitor app-insights component show --app <name> -g <resource_group> --query appId -o tsv`
  turns a component name into the GUID to store. There is no `component
  list`: `show` without `--app` is the list -
  `az monitor app-insights component show --query "[].{name:name, rg:resourceGroup, appId:appId}" -o table`,
  subscription-wide. **An empty group-scoped listing is not an answer**: a
  component often sits in another group than its workspace; widen to
  the subscription-wide form before concluding there is none.

### What to ask the user

One question rather than four:

> Which subscription, resource group, Log Analytics workspace, and
> Application Insights resource should the runs query? (I can resolve
> both GUIDs from their names, and list the candidates if you are unsure.)

The Application Insights part is asked on **every** pass. If `az` is not
logged in, do not turn this into an auth flow: state what will be asked
once the CLI answers, persist what the user does supply, and let
`backend-configuration`'s `## Check` guide the login. "There is no
Application Insights here" is an answer once the user says so or the
subscription-wide listing came back empty: persist nothing for
`app_insights_app` and say what it costs (logs and platform metrics only,
tracing a telemetry gap); never persist a placeholder, never offer to
create the resource. A value the user cannot supply yet stays unpersisted
and reads "not persisted - the mission will ask". Never invent a GUID,
never guess a group from a similar name, never persist a partial GUID.
