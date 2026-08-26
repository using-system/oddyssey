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

## Query by signal

| Signal | How | Link | Notes |
| --- | --- | --- | --- |
| Logs (Log Analytics workspace) | `az monitor log-analytics query --workspace <workspace-GUID> --analytics-query "<KQL>" --timespan P3DT12H` | [az monitor log-analytics query](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics#az-monitor-log-analytics-query) | `--workspace`/`-w` takes the workspace's *customer ID* GUID, not its resource name — get it from `workspace show`. `--timespan` is an ISO 8601 duration/interval; omitted, it queries all available data. `--workspaces` unions extra workspaces into one cross-workspace query. Extension command (auto-installs on first use), GA — the live command index lists `az monitor log-analytics query` as `Extension` / `GA` while the `workspace` and `cluster` subgroups are `Core` / `GA`. |
| Logs (Application Insights) | `az monitor app-insights query --app <GUID\|name> -g <rg> --analytics-query "requests \| summarize count() by bin(timestamp, 1h)" --offset 1h30m` | [az monitor app-insights query](https://learn.microsoft.com/en-us/cli/azure/monitor/app-insights#az-monitor-app-insights-query) | Part of the `application-insights` CLI extension (auto-installs on first use). `--offset` (default `1h`) sets the window ending at `--end-time` (default now) unless `--start-time`/`--end-time` are given explicitly. Also queryable: `az monitor app-insights events show` (single-event lookup by type/ID) and `az monitor app-insights metrics show` (one named metric's value). |
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
- Profiles are a coverage gap on the CLI: `az` can *enable* Application
  Insights Profiler on a .NET/.NET Core web app but cannot read a single
  profile back, and profiler traces live outside the KQL tables. On an
  Azure Monitor backend, treat profiles as UI-only and record the absence
  in the report's Telemetry gaps (verified 2026-08).
- Auth scope: service-principal/managed-identity auth is unaffected by the
  September 2025 MFA mandate for interactive `az login`; plan automation
  (CI, agents) around a service principal or managed identity rather than a
  user identity from the start.
