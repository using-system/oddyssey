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
| Logs (Log Analytics workspace) | `az monitor log-analytics query --workspace <workspace-GUID> --analytics-query "<KQL>" --timespan P3DT12H` | [az monitor log-analytics query](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics#az-monitor-log-analytics-query) | `--workspace`/`-w` takes the workspace's *customer ID* GUID, not its resource name — get it from `workspace show`. `--timespan` is an ISO 8601 duration/interval; omitted, it queries all available data. `--workspaces` unions extra workspaces into one cross-workspace query. Extension command (auto-installs on first use), GA — the live command index lists `az monitor log-analytics query` as `Extension` / `GA` while the `workspace` and `cluster` subgroups are `Core` / `GA`. |
| Logs (Application Insights) | `az monitor app-insights query --app <appId-GUID> --analytics-query "requests \| summarize count() by bin(timestamp, 1h)" --offset 1h30m` | [az monitor app-insights query](https://learn.microsoft.com/en-us/cli/azure/monitor/app-insights#az-monitor-app-insights-query) | Part of the `application-insights` CLI extension (auto-installs on first use). `--app` takes the appId GUID **without** `-g`, or the resource name **with** `-g` — never a GUID and `-g` together, which fails: see the `--app` table above. `--offset` (default `1h`) sets the window ending at `--end-time` (default now) unless `--start-time`/`--end-time` are given explicitly. Also queryable: `az monitor app-insights events show` (single-event lookup by type/ID) and `az monitor app-insights metrics show` (one named metric's value). Under `-o json`, `customDimensions` comes back double-JSON-encoded as a string, not a nested object (verified on az 2.89.1, 2026-08) — project the specific keys you need via KQL (`tostring(customDimensions['x'])`) rather than dumping the whole column. |
| Traces / distributed tracing | KQL against `requests` and `dependencies` tables (Application Insights) or `AppRequests`/`AppDependencies` (Log Analytics) | [Telemetry data model](https://learn.microsoft.com/en-us/azure/azure-monitor/app/data-model-complete) | Read the surprise below — spans live in `requests`/`dependencies`, not `traces`. `operation_Id` (App Insights) / `OperationId` (Log Analytics) correlates a request with its dependency calls into one trace; join or filter on it to reconstruct a call chain. |
| Metrics (Azure Monitor platform metrics) | `az monitor metrics list --resource <name-or-id> --metric "Percentage CPU" --aggregation Average --interval PT1H --start-time <ISO> --end-time <ISO>` | [az monitor metrics list](https://learn.microsoft.com/en-us/cli/azure/monitor/metrics#az-monitor-metrics-list) | `--aggregation` accepts `Average, Count, Maximum, Minimum, None, Total`; `--dimension` splits the series (e.g. by `ApiName`); `--filter` is an OData-style dimension filter (`"ApiName eq '*' and GeoType eq '*'"`). Discover valid metric names/aggregations first with `az monitor metrics list-definitions --resource <id>`, and namespaces with `az monitor metrics list-namespaces` (preview). |
| Profiles | Not readable from `az` — Application Insights Profiler is enabled from the CLI (`az monitor app-insights component connect-webapp -g <rg> -a <app> --web-app <name> --enable-profiler`) but its traces are viewed only in the Azure portal. | [az monitor app-insights component](https://learn.microsoft.com/en-us/cli/azure/monitor/app-insights/component), [View Profiler data](https://learn.microsoft.com/en-us/azure/azure-monitor/profiler/profiler-data) | `--enable-profiler` is documented as "Enable collecting profiling traces that help you see where time is spent in code. Currently it is only supported for .NET/.NET Core Web Apps" — configuration, not a read. Reading is portal-only: **Investigate > Performance > Profiler** (`Profile Now` for an on-demand session), then **Drill into… > Profiler traces** for the profile tree / flame graph. No `az` subcommand and no KQL table return profiler traces, so a terminal-only run cannot see them. |
| Activity log (control-plane/audit events) | `az monitor activity-log list --resource-group <rg> --offset 1h` | [az monitor activity-log list](https://learn.microsoft.com/en-us/cli/azure/monitor/activity-log#az-monitor-activity-log-list) | Subscription-level audit trail (who did what to which resource) — separate from resource logs/metrics and not sent through diagnostic settings by default. `--correlation-id` filters by a specific operation's correlation ID. `list-categories` enumerates the fixed category set: `Administrative, Security, ServiceHealth, Alert, Recommendation, Policy`. |

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
  an auto-installing extension command prints several stderr lines before
  the JSON result on stdout — install/preview `WARNING:`s and, unrelated
  to the extension itself, a `SyntaxWarning` from the `azure-batch`
  module (verified on az 2.89.1, 2026-08). None of it is a failure; a
  caller capturing combined stdout+stderr, or pattern-matching stderr for
  "error"/"warning" as a health signal, will misread this first-use noise
  as one.
- Profiles are a coverage gap on the CLI: `az` can *enable* Application
  Insights Profiler on a .NET/.NET Core web app but cannot read a single
  profile back, and profiler traces live outside the KQL tables. On an
  Azure Monitor backend, treat profiles as UI-only and record the absence
  in the report's Telemetry gaps (verified 2026-08).
- Auth scope: service-principal/managed-identity auth is unaffected by the
  September 2025 MFA mandate for interactive `az login`; plan automation
  (CI, agents) around a service principal or managed identity rather than a
  user identity from the start.
