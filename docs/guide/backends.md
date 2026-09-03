# Backend setup and switch examples

Every value in `STACKS` (`local`, `grafana`, `azure-monitor`,
`cloudwatch`, `datadog`, `dynatrace`, `splunk`) is queried through its
own CLI, and `/odd-config` points a mission at one. Per backend: the
**CLI** and how to install it, how to **connect**, the **resource**
that must already exist before there is anything to query, an example
**switch prompt**, and what `stack_config` **persists**. The source is
each backend's reference under the
[`observability-cli-guides`](../../.apm/skills/observability-cli-guides/SKILL.md)
skill; this page restates it, never extends it. Naming a stack in an
`/odd-observe` mission switches the configuration too.

## local

**CLI**: `gcx` — `brew install gcx`, or the official install script.
The local stack is oddyssey's own container (Grafana, Tempo,
Prometheus, Loki, Pyroscope), brought up by `odd_stack_up`.

**Connect**: nothing — the stack serves its API anonymously, and
oddyssey points gcx at it through an isolated context of its own.

**Resource required**: nothing beyond the container. A fresh machine
targets `local` with no switch at all.

```text
/odd-config switch to local
```

**Persists**: nothing for targeting. `stack_config.local` only holds
the container's environment variables, managed by
`odd_stack_up`/`odd_stack_reset`.

## grafana

**CLI**: `gcx` — `brew install gcx`, or the official install script.
`grafana` always means a remote Grafana (12+, Cloud, Enterprise, or
OSS); the local stack is `local`.

**Connect**: `gcx login <name> --server https://<stack>.grafana.net`
(Cloud) or `gcx config use-context <name>` for an existing context;
`gcx config check` proves it.

**Resource required**: a Grafana instance whose datasources (Loki,
Tempo, Prometheus, Pyroscope) already receive your telemetry.

```text
/odd-config switch to grafana
```

**Persists**: nothing — gcx's active context already names the
instance, org, and datasources.

## azure-monitor

**CLI**: `az` (Azure CLI) — `brew install azure-cli`, or the official
installer; the `log-analytics` and `application-insights` extensions
install on first use.

**Connect**: `az login`, or a service principal for automation.

**Resources required**: a Log Analytics workspace (logs and platform
metrics) and, for tracing, an Application Insights component on that
workspace — without one, tracing is reported as a telemetry gap.

```text
/odd-config switch to azure-monitor, app insights "checkout-appinsights"
/odd-config switch to azure-monitor, subscription "Contoso Prod", resource group "rg-observability", workspace "log-analytics-prod", app insights "checkout-appinsights"
```

**Persists**: `subscription`, `resource_group`, `workspace`, and
`app_insights_app` (the two GUIDs resolved from the names you give).
Naming the Application Insights component is enough in a
single-subscription, single-resource-group setup; name the rest when
there is more than one candidate. "There is no Application Insights
here" is a valid answer.

## cloudwatch

**CLI**: `aws` (AWS CLI v2) — `brew install awscli`, or the official
installer.

**Connect**: `aws sso login --profile <name>`, or `aws configure` for
static keys.

**Resource required**: a CloudWatch Logs log group carrying
application logs; optionally a second log group receiving metrics as
Embedded Metric Format, and X-Ray for traces — none provisioned by
oddyssey.

```text
/odd-config switch to cloudwatch, profile "myteam", region "eu-central-1", log group "/ecs/checkout"
/odd-config switch to cloudwatch, profile "myteam", region "eu-central-1", log group "/ecs/checkout", metrics log group "/ecs/checkout-metrics", xray group "checkout"
```

**Persists**: `region`, `profile`, `log_group`, and optionally
`metrics_log_group` and `xray` — `aws` says who you are, never which
log groups the missions read.

## datadog

**CLI**: Pup — `brew tap datadog-labs/pack && brew install
datadog-labs/pack/pup`, a release binary, or a source build.

**Connect**: `pup auth login`, or `DD_API_KEY`/`DD_APP_KEY` for
non-interactive use; `pup auth status` confirms it by its output.

**Resource required**: nothing beyond an org already receiving your
telemetry.

```text
/odd-observe what did my service XXX do over the last 24 hours on datadog?
```

**Persists**: nothing — the Pup session carries the site and org. A
session on the wrong site returns empty results, not an error.

## dynatrace

**CLI**: `dtctl` — `brew install dynatrace-oss/tap/dtctl`, the
install script, or a release binary.

**Connect**: `dtctl auth login --context <name> --environment
"https://<envid>.apps.dynatrace.com"`; `dtctl auth whoami` proves it.

**Resource required**: nothing beyond an environment already receiving
your telemetry.

```text
/odd-config switch to dynatrace
```

**Persists**: nothing — `dtctl`'s active context names the
environment.

## splunk

**CLI**: `splunk` — ships with the Splunk instance
(`$SPLUNK_HOME/bin/splunk`); for a remote instance, pass `-uri
https://<host>:8089`.

**Connect**: `splunk login`, or `-auth <user>:<password>` per command.

**Resource required**: nothing beyond an instance and index already
receiving your telemetry.

```text
/odd-observe what did my service XXX do over the last 24 hours on splunk?
```

**Persists**: nothing — the instance and user are given per mission.
