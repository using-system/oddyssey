# Backend switch examples

`/odd-config` switches the configured stack — one of the seven values in
`STACKS` (`local`, `grafana`, `azure-monitor`, `cloudwatch`, `datadog`,
`dynatrace`, `splunk`). What a switch persists, if anything, differs a
lot between them: most remote backends' CLI carries its own context and
`stack_config` stays empty; a couple are general-purpose CLIs that need
targeting values persisted so missions don't ask for them on every run.
This page shows, backend by backend, an example switch prompt and
exactly what gets persisted. Source of truth for the persisted fields
is each backend's own `references/<stack>.md` under the
`update-backend-configuration` skill — this page only restates it, never
extends it.

Naming a stack directly in an `/odd-observe` mission switches the
configuration too, the same as going through `/odd-config` first; more
invocation examples for every prompt live in
[prompts.md](prompts.md).

## local

Nothing to persist. `local` is the default stack — a fresh machine
targets it with no switch and no targeting question at all.

```text
/odd-config switch to local
```

## grafana

Nothing persisted. gcx's active context already carries the instance,
org, and datasource defaults — copying any of that into `stack_config`
would create a second truth that drifts the moment the context changes.
Only the CLI needs to be configured beforehand.

```text
/odd-config switch to grafana
```

## azure-monitor

Persists `subscription`, `resource_group`, `workspace` (the Log
Analytics workspace's customer-ID GUID), and `app_insights_app` (the
Application Insights component's appId GUID) — `az` is a
general-purpose CLI that says who you are, never where the telemetry
lives. Both GUIDs are resolved from the names you give, not typed by
hand:

```text
/odd-config switch to azure-monitor, app insights "checkout-appinsights"
```

Naming just the Application Insights component is enough in a
single-subscription, single-resource-group setup — the skill resolves
the rest. Name the other three explicitly when there's more than one
candidate, or when the workspace doesn't share its component's name:

```text
/odd-config switch to azure-monitor, subscription "Contoso Prod", resource group "rg-observability", workspace "log-analytics-prod", app insights "checkout-appinsights"
```

`app_insights_app` is asked on every azure-monitor switch, not only
when raised first — its absence silently degrades a run to logs and
platform metrics only, with distributed tracing reported as a
telemetry gap. "There is no Application Insights here" is a legitimate
answer, never a blank left to fill with a guess.

## cloudwatch

Persists `region`, `profile` (the named `aws` CLI profile to run under
— routinely required, since SSO setups often have no `default`
profile), `log_group` (application logs, or a naming pattern like
`/aws/ecs/<service>`), optionally `metrics_log_group` (a separate log
group metrics arrive through as Embedded Metric Format, when the
account exports them that way), and optionally `xray` (the X-Ray group
or context, when X-Ray is part of the picture). `aws` is a
general-purpose CLI: a profile says which credentials and region, never
which log groups or X-Ray group the missions read.

```text
/odd-config switch to cloudwatch, profile "myteam", region "eu-central-1", log group "/ecs/checkout"
```

Add the metrics log group when the account's exporter writes Embedded
Metric Format records to a group distinct from application logs — it
may or may not be the same value as `log_group`, so it's asked and
persisted separately, never assumed:

```text
/odd-config switch to cloudwatch, profile "myteam", region "eu-central-1", log group "/ecs/checkout", metrics log group "/ecs/checkout-metrics", xray group "checkout"
```

## datadog

Nothing persisted. The Pup CLI's own session carries the site
(`datadoghq.com`, `datadoghq.eu`, …) and org the queries hit — a
session on the wrong site returns **empty results, not an error**, so
confirm the site is right rather than assuming a failure means
misconfiguration.

```text
/odd-observe what did my service XXX do over the last 24 hours on datadog?
```

## dynatrace

Nothing persisted. `dtctl`'s active context already names the
environment the DQL queries run against.

```text
/odd-config switch to dynatrace
```

## splunk

Nothing persisted — there's no shareable context to mirror. The
instance and user are supplied **per mission**, not stored, since the
next mission may legitimately target a different one.

```text
/odd-observe what did my service XXX do over the last 24 hours on splunk?
```
