# Azure Monitor — `az` (Azure CLI)

Official docs: https://learn.microsoft.com/en-us/cli/azure/monitor and
https://learn.microsoft.com/en-us/azure/azure-monitor/
CLI reference pages (`/cli/azure/...`) are HTML but return raw markdown if
you append `?view=azure-cli-latest&accept=text/markdown` to the URL
(confirmed via `content-type: text/markdown` response header); conceptual
docs pages (`/azure/azure-monitor/...`, `/kusto/...`) do not honor that
parameter and stay HTML-only.

## CLI binary

- **Binary**: `az`
- **Detect**: `command -v az`
- **Install**: `brew install azure-cli` (macOS) or the official installer
  per platform: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
  — the `log-analytics`/`application-insights` extensions auto-install on
  first use.

## Setup

| Topic | Link | What to do with it |
| --- | --- | --- |
| Sign in overview | [authenticate-azure-cli](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli) | Four auth options: Cloud Shell (auto), interactive `az login` (browser, picks a default subscription), managed identity, service principal. Starting September 2025 Microsoft requires MFA for user-identity `az login`; this does not affect service principals or managed identities — migrate automation off username/password now. |
| Service principal login | [authenticate-azure-cli-service-principal](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-service-principal) | The recommended auth for scripts/CI. `az login --service-principal --username APP_ID --password CLIENT_SECRET --tenant TENANT_ID`, or `--certificate /path/to/cert.pem` instead of `--password`. Use `--password=CLIENT_SECRET` (with `=`) if the secret starts with `-`. |
| Default subscription | [authenticate-azure-cli](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli#find-or-change-your-current-subscription) | `az account set --subscription "<id-or-name>"` — every subsequent command runs against this subscription unless overridden with `--subscription`. |
| Current context & connection probe | [az account show](https://learn.microsoft.com/en-us/cli/azure/account#az-account-show) | `az account show` displays the active subscription and tenant — the preflight's context display — and errors with a "Please run 'az login'" message when not authenticated, making it the cheapest connection probe too. |
| `az monitor` command group | [az monitor](https://learn.microsoft.com/en-us/cli/azure/monitor) | The root: `log-analytics` (workspaces + KQL query), `app-insights` (extension; components + KQL query), `metrics`, `activity-log`, `diagnostic-settings`, `alert`, `autoscale`. Start here to see what subgroup owns the resource you need. |
| Diagnostic settings | [az monitor diagnostic-settings](https://learn.microsoft.com/en-us/cli/azure/monitor/diagnostic-settings) | Routes a resource's platform logs/metrics to a Log Analytics workspace, storage account, or Event Hub — required before any resource's data is queryable in Log Analytics. |
| Log Analytics workspace management | [az monitor log-analytics workspace](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics/workspace) | Create/list/show workspaces (`az monitor log-analytics workspace create\|list\|show`); `get-schema` dumps the workspace's table schema; `saved-search` manages saved KQL queries. Get the workspace GUID here for `az monitor log-analytics query -w`. |

## Find your Application Insights resource

A Log Analytics workspace alone does not answer APM questions: the
`requests`/`dependencies` tables and the Profiler exist only once an
Application Insights component is provisioned and grafted onto the
workspace. So the component is what the `stack_config` value
`app_insights_app` points at, and this is how to find it.

**There is no `component list`.** `show` without `--app` is the list —
`az monitor app-insights component list` fails with `'list' is
misspelled or not recognized by the system` (verified on az 2.77.0 with
the `application-insights` extension). The listing commands are:

```bash
# every component in a resource group
az monitor app-insights component show -g <rg> \
  --query "[].{name:name, appId:appId, kind:kind}" -o table

# every component in the active subscription
az monitor app-insights component show \
  --query "[].{name:name, rg:resourceGroup, appId:appId}" -o table

# the appId GUID of one named component
az monitor app-insights component show --app <name> -g <rg> \
  --query appId -o tsv
```

`appId` is a **flattened top-level key** of the `show` output (the ARM
model calls it `properties.AppId`), alongside `workspaceResourceId`,
which names the Log Analytics workspace the component writes to.

`show` also returns `instrumentationKey` and `connectionString` at the
same level, and both **are ingestion credentials**. Always project with
`--query`, as every command above does. Never echo the raw component
object into a configuration display, a transcript, or a stored `.odd/`
report — a credential that reaches a committed report is a leak, and
nothing in these commands needs those two fields.

### `--app` takes a GUID **or** a name, never interchangeably

`--app`'s help text ("GUID, app name, or fully-qualified Azure resource
name") is true of `query` and **not** of `component show`, which
resolves `--app` as the ARM resource name only. The two commands also
disagree about `-g`: `show` demands it beside any `--app`, `query`
refuses it beside a GUID. Every row below was run against a live
component on az 2.77.0, 2026-08:

| Form | `component show` | `query` |
| --- | --- | --- |
| `--app <appId GUID>`, no `-g` | ✗ exit 1, `Application provided without resource group` | ✓ exit 0 |
| `--app <appId GUID>` **with** `-g` | ✗ exit 3, `ResourceNotFound` | ✗ exit 3 |
| `--app <name>` with `-g` | ✓ exit 0 | ✓ exit 0 |
| `--app <name>`, no `-g` | ✗ exit 1, `Application provided without resource group` | ✗ exit 1, `The Application Insight is not found. Please check the app id again.` |
| unknown value, otherwise well-formed | ✗ exit 3 | ✗ exit 3 |

Two independent traps, one per command:

- **`show` requires `-g` beside any `--app`** — a client-side check that
  fires before any network call, so rows 1 and 4 are the *same* failure
  and the value's form is irrelevant to it. Given its `-g`, `show` then
  resolves the value as a resource **name**, which is why a correct GUID
  with a correct `-g` still 404s (row 2).
- **`query` forbids `-g` beside a GUID** — read row 2 twice: adding the
  resource group breaks a query that works without it. The GUID is
  self-sufficient and takes no resource group (nor any subscription);
  the name is meaningless without one.

**The persisted value is the GUID, and every ARM read wants the name.**
`stack_config.app_insights_app` is the appId `query` takes; `component
show` — retention, sampling, `workspaceResourceId` — refuses it (row 2).
Resolve the name once from the persisted value, never guess it:
`az monitor app-insights component show --query
"[?appId=='<app_insights_app>'].{name:name, rg:resourceGroup}" -o tsv`
(`--subscription <subscription>` when the persisted one is not az's
active one — an ARM read, unlike the data-plane `query` probe below,
does take it) — subscription-wide on purpose: the component may sit
outside the workspace's `resource_group`, and a `-g`-scoped listing
then answers an empty tsv — and reuse the name and group for every
later `show` of the run (verified 2026-09-05, az 2.89.1).

Exit codes on both commands: 0 success, **3 only for a resource that
does not exist**, **2 when az cannot parse the command** (argparse
fails before any handler runs — a mistyped flag, or `component list`),
and **1 for everything else** — az sets `exit_code = 3` solely for
`ResourceNotFoundError` and defaults every other failure to 1
(`azure/cli/core/util.py`), so authorization failures, expired
credentials, network and proxy errors and throttling are
indistinguishable by code alone. Exit 1 means *read the message*, and
az sometimes wraps it in an "unexpected error … Here is the traceback"
banner: the `ERROR:` line is the diagnosis, not the stack below it.

## Query by signal

| Signal | How | Link | Notes |
| --- | --- | --- | --- |
| Logs (Log Analytics workspace) | `az monitor log-analytics query --workspace <workspace-GUID> --analytics-query "<KQL>" --timespan P3DT12H` | [az monitor log-analytics query](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics#az-monitor-log-analytics-query) | `--workspace`/`-w` takes the workspace's *customer ID* GUID, not its resource name — get it from `workspace show`. `--timespan` is an ISO 8601 duration/interval; omitted, it queries all available data. `--workspaces` unions extra workspaces into one cross-workspace query. `-o json` returns a **flat list of row objects** carrying a `TableName` key, with the values stringified (`"n": "484782"`) — unlike `app-insights query`'s `{"tables": [{"columns": [...], "rows": [[484786]]}]}` with typed values; one parser does not fit both (verified 2026-09-05). Aliases: never `first`/`last` (`BadArgumentError`), `earliest`/`latest` — the reserved-word trap of the Planning notes. Extension command (auto-installs on first use), GA — the live command index lists `az monitor log-analytics query` as `Extension` / `GA` while the `workspace` and `cluster` subgroups are `Core` / `GA`. |
| Logs (Application Insights) | `az monitor app-insights query --app <appId-GUID> --analytics-query "requests \| summarize count() by bin(timestamp, 1h)" --offset 1h30m` | [az monitor app-insights query](https://learn.microsoft.com/en-us/cli/azure/monitor/app-insights#az-monitor-app-insights-query) | Part of the `application-insights` CLI extension (auto-installs on first use). `--app` takes the appId GUID **without** `-g`, or the resource name **with** `-g` — never a GUID and `-g` together, which fails: see the `--app` table above. `--offset` (default `1h`) sets the window ending at `--end-time` (default now) unless `--start-time`/`--end-time` are given explicitly. Also queryable: `az monitor app-insights events show` (single-event lookup by type/ID) and `az monitor app-insights metrics show` (one named metric's value). Under `-o json`, `customDimensions` comes back double-JSON-encoded as a string, not a nested object (verified on az 2.89.1, 2026-08, and again 2026-09-04: a `tostring(customDimensions['user_agent.original']) != ''` filter matched 6666 rows) — project the specific keys you need via KQL (`tostring(customDimensions['x'])`) rather than dumping the whole column. `--offset` also bounds a query that carries its **own** `timestamp between (...)` filter: a window older than the offset returns 0 rows with no error (verified 2026-09-04: a 3h-to-2h-ago window gave 0 rows under the default `1h`, 6766 with `--offset 4h` or with `--start-time`/`--end-time`) — make the offset cover the window, or pass the pair. `-o json` is `{"tables": [{"columns": [...], "rows": [[...]]}]}` with typed values — not the flat, stringified list `log-analytics query` returns (see that row above). Aliases: never `first`/`last` (`BadArgumentError`), `earliest`/`latest`. `\| count` read under `-o tsv` prints **1** whatever the count — the number of result rows, never the value (verified 2026-09-05: `1` for 113 rows and `1` for 0) — read it with `-o json` at `tables[0].rows[0][0]`, or `summarize n=count()` through `--query 'tables[0].rows[0][0]' -o tsv`. |
| Traces / distributed tracing | KQL against `requests` and `dependencies` tables (Application Insights) or `AppRequests`/`AppDependencies` (Log Analytics) | [Telemetry data model](https://learn.microsoft.com/en-us/azure/azure-monitor/app/data-model-complete) | Read the surprise below — spans live in `requests`/`dependencies`, not `traces`. `operation_Id` (App Insights) / `OperationId` (Log Analytics) correlates a request with its dependency calls into one trace; join or filter on it to reconstruct a call chain. |
| Metrics (Azure Monitor platform metrics) | `az monitor metrics list --resource <name-or-id> --metric "Percentage CPU" --aggregation Average --interval PT1H --start-time <ISO> --end-time <ISO>` | [az monitor metrics list](https://learn.microsoft.com/en-us/cli/azure/monitor/metrics#az-monitor-metrics-list) | `--aggregation` accepts `Average, Count, Maximum, Minimum, None, Total`; `--dimension` splits the series (e.g. by `ApiName`); `--filter` is an OData-style dimension filter (`"ApiName eq '*' and GeoType eq '*'"`). Discover valid metric names/aggregations first with `az monitor metrics list-definitions --resource <id>`, and namespaces with `az monitor metrics list-namespaces` (preview). |
| Profiles | Not readable from `az` — Application Insights Profiler is enabled from the CLI (`az monitor app-insights component connect-webapp -g <rg> -a <app> --web-app <name> --enable-profiler`) but its traces are viewed only in the Azure portal. | [az monitor app-insights component](https://learn.microsoft.com/en-us/cli/azure/monitor/app-insights/component), [View Profiler data](https://learn.microsoft.com/en-us/azure/azure-monitor/profiler/profiler-data) | `--enable-profiler` is documented as "Enable collecting profiling traces that help you see where time is spent in code. Currently it is only supported for .NET/.NET Core Web Apps" — configuration, not a read. Reading is portal-only: **Investigate > Performance > Profiler** (`Profile Now` for an on-demand session), then **Drill into… > Profiler traces** for the profile tree / flame graph. No `az` subcommand and no KQL table return profiler traces, so a terminal-only run cannot see them. |
| Activity log (control-plane/audit events) | `az monitor activity-log list --resource-group <rg> --offset 1h` | [az monitor activity-log list](https://learn.microsoft.com/en-us/cli/azure/monitor/activity-log#az-monitor-activity-log-list) | Subscription-level audit trail (who did what to which resource) — separate from resource logs/metrics and not sent through diagnostic settings by default. `--correlation-id` filters by a specific operation's correlation ID. `list-categories` enumerates the fixed category set: `Administrative, Security, ServiceHealth, Alert, Recommendation, Policy`. |

`az monitor` query commands are **safe to run concurrently against one
login**: backgrounded in one shell call, they share the cached token
without contention — four `app-insights query` and two
`log-analytics query` calls all exited 0 with their rows in 2.1 s
against 4.0 s serial (verified 2026-09-04, azure-cli 2.89.1, a
workspace and an Application Insights resource carrying real data).
The batch runs under `bash -c` or from a `#!/bin/bash` helper file,
never as bare lines in the host's shell, which may be zsh: there a KQL
`$CD['user_agent.original']` inside a double-quoted
`--analytics-query` is a subscript, and the line aborts with
`bad math expression: operand expected`, exit 1, before `az` runs —
where the literal `customDimensions[...]`, or `${CD}[...]`, sends the
query as written.

## Planning notes

- **The trace story is not the `traces` table.** Application Insights keeps
  the `traces`/`AppTraces` table for legacy `printf`-style log statements
  only; distributed-tracing spans for incoming requests and outgoing
  dependency calls are stored in `requests`/`AppRequests` and
  `dependencies`/`AppDependencies` — query those two and correlate on
  `operation_Id` to reconstruct a trace (per the fetched data-model page,
  verified 2026-08).
- **A workspace alone cannot answer APM questions.** Application Insights
  is not an enhancement layered on Azure Monitor for this use case — it is
  what makes distributed tracing queryable at all. Without a component,
  `requests`/`dependencies` (and `AppRequests`/`AppDependencies`) are not
  there to query and the Profiler does not exist, so a run against
  `azure-monitor` sees logs and platform metrics only. That absence is a
  **telemetry gap to record in the report**, never something to work
  around by falling back to workspace tables and staying quiet about it.
- KQL (Kusto Query Language) is the single query language across Log
  Analytics and Application Insights — same syntax, different table/field
  names between the two (e.g. `requests.duration` vs `AppRequests.DurationMs`).
  `az monitor log-analytics query` and `az monitor app-insights query` both
  take a raw KQL string via `--analytics-query`; there is no separate KQL
  CLI.
- `az monitor app-insights *` lives in the `application-insights` CLI
  extension (auto-installed, not in CLI core); `az monitor log-analytics *`
  is a mix — `query` itself is an extension command while `workspace`
  management is core GA. Expect a one-time extension install on first use
  in a fresh environment.
- **That first-use install is noisy, not broken.** The first invocation of
  an auto-installing extension command prints several install/preview
  `WARNING:` lines to stderr before the JSON result on stdout, exit code
  0 (verified on az 2.89.1, 2026-08, both `log-analytics query` and
  `app-insights query`). Some environments also print an unrelated
  `SyntaxWarning` from the `azure-batch` module during this first
  install — not reproduced in every environment, so treat it as possible
  rather than guaranteed. None of it is a failure; a caller capturing
  combined stdout+stderr, or pattern-matching stderr for
  "error"/"warning" as a health signal, will misread this first-use noise
  as one.
- Profiles are a coverage gap on the CLI: `az` can *enable* Application
  Insights Profiler on a .NET/.NET Core web app but cannot read a single
  profile back, and profiler traces live outside the KQL tables. On an
  Azure Monitor backend, treat profiles as UI-only and record the absence
  in the report's Telemetry gaps (verified 2026-08).
- **Ingest latency is seconds to tens of seconds, never a fixed
  sleep.** On a continuously driven service the newest `requests` row
  lagged the clock by 4 to 8 s across three reads 20 s apart (verified
  2026-09-04); a driven run of 110 requests was complete on its first
  poll 25 s after the last request (2026-09-03). Wait by polling a
  run-identity count — `requests | where timestamp between (<start> ..
  <end>) and tostring(customDimensions['user_agent.original']) ==
  '<identity>' | count` every ~20 s, capped at ~3 min — until it
  reaches the request count, then query. Read that count in `-o json`
  (`tables[0].rows[0][0]`), never in `-o tsv`, which prints `1` — one
  result row — whatever the value (verified 2026-09-05): a poll read
  that way "succeeds" on absent rows.
- **`has 'error'` on collector console lines matches info-level
  lines**: the collector's `info` `Exporting failed. Will retry the
  request after interval.` lines carry a JSON `"error": ...` field and
  match the term (verified 2026-09-05: 17 such `info` lines over 7
  days, the collector's levels being `info` and `warn` only). Rule
  collector health on the level column, scoped to the collector's
  container — the level is the second whitespace-separated field of
  its console line; on Azure Container Apps the table is
  `ContainerAppConsoleLogs_CL` and `ContainerName_s` its container
  column — another host substitutes its own:
  `ContainerAppConsoleLogs_CL | where ContainerName_s == '<collector>' | extend lvl=extract(@'^\S+\s+(\w+)\s', 1, Log_s) | where lvl == 'error'`
  — next to the term grep, never instead of it.
- **KQL aliases that are reserved words fail without naming the
  word**: `summarize first=min(timestamp), last=max(timestamp)` is
  refused (`BadArgumentError: The request had some invalid
  properties` from the CLI, the service's `SYN0002` behind it) while
  `earliest=`/`latest=` run (verified 2026-09-04). And a **named**
  `arg_max`/`arg_min` keeps its extra columns' original names —
  `summarize latest=arg_max(timestamp, value), earliest=arg_min(timestamp, value)`
  yields `latest, value, earliest, value1`, not `latest_value` — so a
  delta is `value - value1` (verified 2026-09-04).
- **`customMetrics` temporality: detect before trusting.** When the
  Collector converts to deltas, each row is one export's increment
  (`valueCount` 1, small non-monotonic values: 115 decreases over 300
  pushes, maximum 7, on 2026-09-04) and `sum(value)` over a window is
  the count. When it does not, the rows are running totals per series
  — reported from a 2026-09-03 run on the same pipeline before its
  conversion, not re-observed since — and `sum(value)` multiplies the
  total by the export count, the trap any cumulative pipeline sets.
  Probe one series first:
  `customMetrics | where name == '<name>' | order by timestamp asc | serialize | extend prev = prev(value) | summarize pushes=count(), decreases=countif(value < prev), vmax=max(value) by inst=tostring(customDimensions['service.instance.id'])`
  — decreases near zero with a magnitude beyond any per-interval count
  means cumulative: read the window as an edge delta per series,
  `summarize latest=arg_max(timestamp, value), earliest=arg_min(timestamp, value) by inst=tostring(customDimensions['service.instance.id']) | extend delta = value - value1`
  (the column names above), qualified by `service.instance.id` so a
  restart never reads as a drop.
- Auth scope: service-principal/managed-identity auth is unaffected by the
  September 2025 MFA mandate for interactive `az login`; plan automation
  (CI, agents) around a service principal or managed identity rather than a
  user identity from the start.

## Configuration display

### Display

Two sources, and every line says which one it came from — the CLI
identity and the persisted targeting values are different facts and a
mismatch between them is exactly what this display exists to catch.

From `az account show` (the CLI's own context):

- the active subscription (name and id) and the tenant.

From `stack_config.azure-monitor` (persisted by the user through
`odd_config_set`, per `odd_config_get`):

- `subscription` — the subscription the mission queries, when it is
  pinned separately from the CLI's active one.
- `resource_group` — the resource group holding the workspace; the
  Application Insights component may sit in another one.
- `workspace` — the Log Analytics **customer ID** GUID, the value
  `az monitor log-analytics query` takes as `--workspace`; not the
  workspace resource name.
- `app_insights_app` — the Application Insights component's **appId**
  GUID, the value `az monitor app-insights query` takes as `--app`; not
  the component's resource name.

Show each stored value next to the field it came from. Every field the
user did not persist is listed as "not persisted — the mission will
ask": a present-but-empty `stack_config.azure-monitor` (`{}`) means all
four are unset, which is a valid state, not an error. Say it plainly
when the persisted `subscription` differs from the one `az account
show` reports — the query targets the persisted one.

`app_insights_app` is the one exception to that neutral wording. A
workspace carries logs and platform metrics; distributed tracing lives
in the `requests`/`dependencies` tables, which exist only inside an
Application Insights component. So when `app_insights_app` is unset,
the line is a **named degradation**, not a shrug:

> no Application Insights configured — `requests`/`dependencies` and the
> Profiler are unavailable, and the run will see Log Analytics tables
> only. Distributed tracing will be reported as a telemetry gap.

The mission carries that sentence into the report's telemetry gaps. Say
it whether the user declined the resource or was never asked: the
consequence for the run is identical, and stating it is what stops an
observation from quietly degrading into a logs-only run that reads like
a complete one.

Add any `invalid_ignored` dotted names as degradations: the stored
value was invalid and was dropped. `stack_config` has no defaults behind
it, so a dropped value reads as not persisted — nothing silently took
its place.

### Connection proof

This section defines the probe the skill's step 3 runs, and it has
**two parts**, because `az` answering says nothing about whether the
persisted target exists. A successful identity proof alone is not a
connected verdict when `app_insights_app` is persisted: both parts must
pass. The second is skipped — not failed — when nothing is persisted to
check.

**Identity** — `az account show` succeeding. It doubles as the context
display: unauthenticated, it fails with a "Please run 'az login'"
message. Never run `az login` for the user: guide it.

**Targeting** — when `app_insights_app` is persisted, prove the GUID
resolves before a mission spends a run on it:

```bash
az monitor app-insights query --app <app_insights_app> \
  --analytics-query "print 1" --offset 5m -o none
```

Exit 0 is the proof (about a second against a live component). This
queries the data plane rather than reading the resource through ARM,
which is deliberate: it proves the access a mission actually needs, and
an identity with query rights but no ARM read still passes. The appId
resolves on the data plane and carries no subscription, so a
persisted/active subscription mismatch does not affect this proof —
**do not add `--subscription`** to reconcile it (verified: the probe
returns exit 0 even under a subscription that does not exist).

Two things this command will not tolerate, both verified on az 2.77.0:
**never add `-g` beside the GUID** — the pair fails with exit 3 even
when both values are correct — and never substitute the component's
resource name. A name would need a `-g` this probe does not pass, and
proving a name proves nothing about the GUID that is actually stored.
The `--app` table earlier in this file has the full matrix.

**Read the error line before diagnosing — the exit code alone is not
enough.** az reserves exit **3** for one thing, a resource that does not
exist (`ResourceNotFoundError`), and funnels almost everything else into
exit **1**: authorization failures, expired credentials, network and
proxy errors, throttling and service errors alike
(`azure/cli/core/util.py`, az 2.77.0 — `exit_code = 1` is the default
and `3` is set only for `ResourceNotFoundError`). So:

- **Exit 0** — connected, the persisted appId resolves and is queryable.
- **Exit 3** — the appId does not resolve. This is the wrong-value case:
  stop, report the persisted GUID as unresolvable, and route to
  `backend-configuration`'s `## Switch` to correct it. Catching it here is far
  cheaper than in an observation that returns empty trace queries and
  looks merely quiet.
- **Exit 1** — read the message, and mind that az may wrap it in an
  "unexpected error … Here is the traceback" banner: the diagnosis is
  the `ERROR:` line, never the Python stack under it. `The Application
  Insight is not found. Please check the app id again.` means the
  persisted value is not an appId GUID — typically the component's
  resource name, which this probe cannot resolve without a `-g` it does
  not pass. That is a wrong value: route once, exactly as exit 3. An
  authorization/`Forbidden` message instead means the identity is
  authenticated but lacks **query rights** on this component — a
  permissions problem, **not** a wrong value: re-persisting the same
  correct GUID will not fix it, so say that plainly and name the missing
  access rather than routing. A re-authentication message (`AADSTS…`, or
  a "run `az login`") is an **identity** failure surfacing late: `az
  account show` reads the local profile and never touches the network,
  so it returns 0 on a stale token and only this probe reveals it. Hand
  it to the identity guidance above — do not retry it, and do not route
  it to `backend-configuration`'s `## Switch`, which cannot fix a login.
  Anything else (connection, proxy, throttling, service error) is
  reported verbatim and retried; never rewrite it as a targeting
  failure.
- **Exit 2** — az could not parse the command. That is a defect in the
  command as written, not a configuration problem and never a wrong
  stored value: fix the invocation against the reference.

Exit 1 is a bucket, not a diagnosis: mistaking a 403 for a bad GUID
sends the user to re-persist a value that was right all along, and
mistaking a stored name for a transient error retries it forever.

A failed targeting proof is **not** a "CLI not configured" error and is
never reported as one: the binary is installed, `az` is authenticated,
and the backend answered. What is wrong is the stored value or the
access to it — say it in those terms. Route to
`backend-configuration`'s `## Switch` **once** for a corrected value; if the
proof fails again on the value that came back, stop and report rather
than bouncing between the two skills.

`app_insights_app` unset is **not** a failed proof: it is the
degradation stated in the display above, and the mission proceeds
logs-only having said so.

### Change-request phrasing

- "persist workspace <guid> for azure-monitor"
- "persist app insights <name-or-guid> for azure-monitor"
- "clear the workspace for azure-monitor"
- "change backend to azure-monitor"

## What to persist

### What stack_config holds

`az` is a **general-purpose** CLI: its context says who you are and
which subscription is active, and nothing at all about where the
telemetry lives. A Log Analytics query needs a workspace GUID that no
`az` context carries. So `stack_config.azure-monitor` holds the
targeting information the missions would otherwise ask for on every
single run:

- `subscription` — the subscription the missions query, by name or id.
- `resource_group` — the resource group holding the workspace. The
  Application Insights component may well sit in another one; this field
  pins the workspace's.
- `workspace` — the Log Analytics workspace's **customer ID** GUID: the
  value `az monitor log-analytics query` takes as `--workspace`. Not the
  workspace resource name, which looks plausible in the same slot and
  fails.
- `app_insights_app` — the Application Insights component's **appId**
  GUID: the value `az monitor app-insights query` takes as `--app` with
  no `-g` beside it. Not the resource name, which needs a resource group
  to mean anything, and not the instrumentation key.

The workspace and the component are two different things and the runs
need both. A workspace holds logs and platform metrics; the
`requests`/`dependencies` tables that carry distributed tracing exist
only once an Application Insights component is provisioned and grafted
onto that workspace. Persisting a workspace and no component configures
a run that can read logs and cannot see a single trace — which is why
`app_insights_app` is asked for on every azure-monitor pass rather than
waited for.

All four are identifiers and names. None of them is a secret: the
credential behind `az` stays in its own auth store, established by
`az login`, and is never copied here.

### Where each value comes from

- `subscription` — `az account show` reports the active subscription's
  name, id, and tenant. If the missions target that one, take it from
  there; persist it anyway, because "active" is machine state that
  changes under you and the stored value is what pins the target.
- `resource_group` — list the workspaces the identity can see and read
  the group each sits in. The exact listing command comes from the
  `## Setup` table earlier in this file, or from
  `az monitor log-analytics workspace --help` — never from memory.
- `workspace` — `az monitor log-analytics workspace show -g
  <resource_group> -n <name> --query customerId -o tsv` is the command
  that turns a workspace name into the GUID to store. Deriving it is
  strictly better than asking: users know their workspace by name and
  rarely by GUID.
- `app_insights_app` — `az monitor app-insights component show --app
  <name> -g <resource_group> --query appId -o tsv` turns a component
  name into the GUID to store, exactly as the workspace command turns a
  workspace name into its customer ID. When the user does not know which
  component to name, list them first —
  `az monitor app-insights component show -g <resource_group> --query
  "[].{name:name, appId:appId}" -o table` — and note there is no
  `component list` subcommand; the discovery block earlier in this
  file has the full command set.
  **An empty listing is not an answer.** A component often sits in a
  different resource group from the workspace it writes to, and a
  group-scoped listing that finds nothing returns an empty table with
  exit 0 — indistinguishable, at a glance, from a subscription that has
  no Application Insights at all. Always widen to the subscription-wide
  form (`component show --query "[].{name:name, rg:resourceGroup,
  appId:appId}" -o table`, which reports each component's own group)
  before concluding there is none. Concluding "no Application Insights"
  from a narrow listing persists the degradation this field exists to
  prevent.

### What to ask the user

Ask for **every value that is not derivable** from `az account show` and
the list commands above, one question rather than four:

> Which subscription, resource group, Log Analytics workspace, and
> Application Insights resource should the runs query? (I can resolve
> both GUIDs from their names, and list the candidates if you are
> unsure.)

The Application Insights part of that question is asked on **every**
azure-monitor pass, not only when the user brings it up first. It is
the one value a user is least likely to volunteer and the one whose
absence costs the most — see above.

If `az` is not yet logged in, do not turn this into an auth flow: state
what will be asked once the CLI answers, persist what the user does
supply, and let `backend-configuration`'s `## Check` guide the login.

**"There is no Application Insights here" is an answer, not a blank** —
once the user says so outright, or the subscription-wide listing has
come back empty too. Some Azure Monitor deployments genuinely collect
infrastructure logs and platform metrics and nothing else. Take that
answer, persist nothing for
`app_insights_app`, and say plainly what it costs: the runs will read
logs and metrics and will report distributed tracing as a telemetry gap.
Do not persist a placeholder to fill the slot, and do not offer to
create the resource — provisioning Azure infrastructure is not this
skill's job.

A value the user cannot supply yet is left unpersisted — that field
simply reads "not persisted — the mission will ask". Every field except
`app_insights_app`, whose unset state is the named degradation stated
above and never a neutral blank. Never invent a GUID, never guess a
resource group from a name that looks similar, and never persist a
partial GUID.
