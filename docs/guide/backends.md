# Backend setup and switch examples

Every value in `STACKS` (`local`, `grafana`, `azure-monitor`,
`cloudwatch`, `datadog`, `dynatrace`, `splunk`) is queried through its
own CLI, and `/odd-config` is how a mission points at one. This page
covers, backend by backend: the **CLI** and how to install it, what
**resource** needs to already exist on that backend before it has
anything to query — "nothing" is stated explicitly where that's true,
never left silent — an example **switch prompt**, and exactly what
`stack_config` **persists**, if anything. Source of truth is each
backend's own `references/<stack>.md` under the
`observability-cli-guides` and `update-backend-configuration` skills —
this page only restates them, never extends them.

Naming a stack directly in an `/odd-observe` mission switches the
configuration too, the same as going through `/odd-config` first; more
invocation examples for every prompt live in
[prompts.md](prompts.md).

## local

**CLI**: `gcx` — `brew install gcx`, or the official install script /
prebuilt binaries. The local stack is oddyssey's own (Grafana, Tempo,
Prometheus, Loki, Pyroscope in one container, brought up by
`odd_stack_up`); gcx queries it the same way it queries a remote
Grafana.

**Connect**: nothing to connect — the local stack serves its API
anonymously, and `setup-local-stack` points gcx at it with an isolated
context it manages itself, never the user's own gcx config.

**Resource required**: nothing beyond the container itself — `local`
is the default and self-contained, no external account or resource to
provision. A fresh machine targets it with no switch and no targeting
question at all.

```text
/odd-config switch to local
```

Nothing is persisted for targeting — the only thing `stack_config.local`
ever holds is the otel-lgtm container's own environment variables,
managed by `odd_stack_up`/`odd_stack_reset`, not by a switch.

## grafana

**CLI**: `gcx` — `brew install gcx`, or the official install script /
prebuilt binaries. `grafana` here always means a **remote** Grafana
(12+, Cloud/Enterprise/OSS) — the local stack is the separate `local`
value above.

**Connect**: if not already done, authenticate gcx against your
instance first — `gcx login <name> --server https://<stack>.grafana.net`
(Cloud) or `gcx config use-context <name>` for an existing on-prem
context. `gcx config check` proves it's connected before any mission
runs.

**Resource required**: a Grafana instance with its datasources (Loki,
Tempo, Prometheus, Pyroscope) already wired up and receiving your
telemetry — gcx queries them, it does not create them.

```text
/odd-config switch to grafana
```

Nothing persisted. gcx's active context already carries the instance,
org, and datasource defaults — copying any of that into `stack_config`
would create a second truth that drifts the moment the context
changes. Only the CLI needs to be configured beforehand.

## azure-monitor

**CLI**: `az` (Azure CLI) — `brew install azure-cli`, or the official
installer per platform. The `log-analytics` and `application-insights`
extensions auto-install on first use.

**Connect**: if not already done, `az login` (interactive) or a
service principal (`az login --service-principal ...`, the recommended
path for automation) before anything else works.

**Resources required**: a **Log Analytics workspace** (logs and
platform metrics) and, for distributed tracing, an **Application
Insights** component grafted onto that workspace — without one, a run
reads logs and metrics only, with tracing reported as a telemetry gap,
not silently skipped.

```text
/odd-config switch to azure-monitor, app insights "checkout-appinsights"
```

Persists `subscription`, `resource_group`, `workspace` (the Log
Analytics workspace's customer-ID GUID), and `app_insights_app` (the
Application Insights component's appId GUID) — `az` is a
general-purpose CLI that says who you are, never where the telemetry
lives. Both GUIDs are resolved from the names you give, not typed by
hand. Naming just the Application Insights component is enough in a
single-subscription, single-resource-group setup — the skill resolves
the rest. Name the other three explicitly when there's more than one
candidate, or when the workspace doesn't share its component's name:

```text
/odd-config switch to azure-monitor, subscription "Contoso Prod", resource group "rg-observability", workspace "log-analytics-prod", app insights "checkout-appinsights"
```

`app_insights_app` is asked on every azure-monitor switch, not only
when raised first. "There is no Application Insights here" is a
legitimate answer, never a blank left to fill with a guess.

## cloudwatch

**CLI**: `aws` (AWS CLI v2) — `brew install awscli`, or the official
installer per platform.

**Connect**: if not already done, `aws sso login --profile <name>`
(SSO, the common case) or `aws configure` (static keys) before
anything else works — a bare `aws sts get-caller-identity` with no
resolvable profile fails even on a fully configured CLI, see the
`observability-cli-guides` reference for that trap.

**Resource required**: at least one **CloudWatch Logs log group**
carrying application logs. Optionally a second, separate log group
metrics arrive through as Embedded Metric Format, and X-Ray enabled if
traces are part of the picture — none of these are provisioned by
oddyssey, they must already exist and be receiving data.

```text
/odd-config switch to cloudwatch, profile "myteam", region "eu-central-1", log group "/ecs/checkout"
```

Persists `region`, `profile` (the named `aws` CLI profile to run under
— routinely required, since SSO setups often have no `default`
profile), `log_group` (application logs, or a naming pattern like
`/aws/ecs/<service>`), optionally `metrics_log_group` (when the
account exports metrics as Embedded Metric Format to a group distinct
from application logs — it may or may not be the same value as
`log_group`, so it's asked and persisted separately, never assumed),
and optionally `xray` (the X-Ray group or context). `aws` is a
general-purpose CLI: a profile says which credentials and region,
never which log groups or X-Ray group the missions read.

Name the metrics log group and the X-Ray group too when they're part
of the picture:

```text
/odd-config switch to cloudwatch, profile "myteam", region "eu-central-1", log group "/ecs/checkout", metrics log group "/ecs/checkout-metrics", xray group "checkout"
```

## datadog

**CLI**: Pup — `brew tap datadog-labs/pack && brew install
datadog-labs/pack/pup`, a prebuilt release binary, or `cargo build
--release` from source.

**Connect**: if not already done, `pup auth login` (interactive,
opens a browser) — or `DD_API_KEY`/`DD_APP_KEY` for non-interactive
use. `pup auth status` confirms it, by its output, never its exit code
(pup exits 0 even unauthenticated).

**Resource required**: nothing beyond an org already receiving your
telemetry — no separate resource to name or provision, the Pup
session's site/org is the whole target.

```text
/odd-observe what did my service XXX do over the last 24 hours on datadog?
```

Nothing persisted. The Pup CLI's own session carries the site
(`datadoghq.com`, `datadoghq.eu`, …) and org the queries hit — a
session on the wrong site returns **empty results, not an error**, so
confirm the site is right rather than assuming a failure means
misconfiguration.

## dynatrace

**CLI**: `dtctl` — `brew install dynatrace-oss/tap/dtctl`, the
install.sh script, or a release binary.

**Connect**: if not already done, `dtctl auth login --context <name>
--environment "https://<envid>.apps.dynatrace.com"` (OAuth,
recommended) before anything else works. `dtctl auth whoami` doubles
as the connection proof.

**Resource required**: nothing beyond an environment already receiving
your telemetry — no separate resource to name, `dtctl`'s active
context names the environment.

```text
/odd-config switch to dynatrace
```

Nothing persisted. `dtctl`'s active context already names the
environment the DQL queries run against.

## splunk

**CLI**: `splunk` — ships with the Splunk Enterprise/Cloud instance
(`$SPLUNK_HOME/bin/splunk`), not separately installable; for a remote
instance, run it on the instance or remotely with `-uri
https://<host>:8089`.

**Connect**: if not already done, `splunk login` once (interactive
session), or pass `-auth <user>:<password>` per command for a
one-off. There's no whoami surface — any trivial authenticated call
(a `search` with `-maxout 1`) is the connection proof.

**Resource required**: nothing beyond an instance/index already
receiving your telemetry — no separate resource to name.

```text
/odd-observe what did my service XXX do over the last 24 hours on splunk?
```

Nothing persisted — there's no shareable context to mirror. The
instance and user are supplied **per mission**, not stored, since the
next mission may legitimately target a different one.
