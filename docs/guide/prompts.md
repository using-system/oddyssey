# Prompt usage examples

Every oddyssey prompt takes free-form arguments: you describe the
mission in plain words, and the prompt maps them onto the fields its
agent or skill expects. This page shows what good invocations look
like, and which mission field each part of the sentence feeds.

The architecture behind these entry points is mapped in
[dependencies.md](dependencies.md).

## /odd-instrument

Investigates a codebase and returns every input needed to plan
OpenTelemetry instrumentation. Free-form arguments map to: the **path
or repository** to investigate (default: the current repository) and
the intended **export stack** (default: the local oddyssey stack).

```text
/odd-instrument add OpenTelemetry to this repository
/odd-instrument my stack has no telemetry at all - start from scratch, everything exports to the local stack
/odd-instrument add OpenTelemetry to services/checkout, we already emit some custom Prometheus metrics
/odd-instrument migrate services/api from winston logging to OpenTelemetry logs, keep the existing log statements
/odd-instrument instrument this repo for a remote Grafana stack, and plan a contrib Collector deployed via Terraform as the gateway
/odd-instrument my agent under src/assistant is built on LangChain - plan GenAI observability with the gen_ai semantic conventions for its LLM calls
```

- "this repository" / "services/checkout" - the investigated path;
- "to the local stack" / "for a remote Grafana stack" - the export
  stack;
- everything else (existing telemetry, the logging library to migrate
  from, the Collector shape, the GenAI framework) is context the
  investigation verifies and turns into per-service decisions or open
  spec questions.

## /odd-observe

Observes a running service through its telemetry and returns the
plan-ready observation report. Free-form arguments map to: **service
name(s)**, **stack** (defaults to the configured one), **mode**
(`drive` / `observe` / `post-hoc`), **window**, **focus**, and
**baseline expectations**. The deployment environment is never an
argument - the agent detects it from the service's telemetry.

> **Important** - the target stack's observability CLI must be
> configured and connected beforehand: the preflight proves the
> connection and fails fast otherwise, it never authenticates for you.
> To switch stacks (say from `local` to `grafana`), go through
> `/odd-config` first - it owns the guided switch (CLI presence,
> install offer, targeting values). Naming a stack in the mission also
> switches the configuration, but `/odd-config` is the guided path.

```text
/odd-observe check that checkout starts and answers requests on the /user endpoint
/odd-observe drive a 50-request scenario against payment on the local stack, focus on latency
/odd-observe someone is load-testing checkout right now - observe the run until I say stop
/odd-observe post-hoc: what did orders do between 14:00 and 15:00 UTC?
/odd-observe switch to grafana and observe checkout, focus on errors
/odd-observe observe checkout after my last deployment, error rate should stay under 1%
/odd-observe list the services with metrics on my stack grafana over the last 30 days - just the names
```

- "checkout", "payment", "orders" - the services;
- "on the local stack" / "switch to grafana" - the stack (one of the
  seven configured values; a named stack is persisted as the new
  configured one); the backend queried is otherwise the configured
  one - `/odd-config` is the guided way to switch;
- if the observability stack is shared across deployment environments
  (one Grafana receiving prod AND uat), mention the environment in
  your prompt - the value the service reports in its
  `deployment.environment.name` resource attribute. It is never a
  mission input (the agent detects the real one from the telemetry)
  but an expectation it reconciles, flagging any divergence;
- "drive a ... scenario" / "observe the run" / "post-hoc" - the mode;
- "list the services with metrics ..." - a discovery ask: the remote
  telemetry can be questioned directly (which services exist, over
  what window) and answered with the query as evidence, without a full
  observation report; naming the stack here still switches the
  configuration like any mission;
- "between 14:00 and 15:00 UTC" / "after my last deployment" - the
  window;
- "focus on latency" / "error rate should stay under 1%" - focus and
  baseline expectations.

## /odd-verify

Replays a stored report's protocol and rules on everything it
recorded. Free-form arguments map to: the **report to verify against**
(a path under `.odd/`, or enough of a run name to find it - observation
or instrumentation report), and, for a remote stack, the **access
material** the agent needs. With no report named, the newest stored
report is picked.

> **Important** - a verify run replays the **report's** stack, never
> silently retargeting the configured one, so that stack's CLI must be
> configured and connected beforehand (the preflight proves it and
> fails fast otherwise). If your CLI currently points elsewhere, go
> through `/odd-config` to set it up for the report's stack before
> verifying.

```text
/odd-verify
/odd-verify check that report checkout-latency-sweep has been fixed
/odd-verify replay .odd/observe-run-reports/2026-08-26-1003-config-set-env-preservation.md
/odd-verify verify my last report for checkout
/odd-verify verify my last prod report
/odd-verify verify the instrumentation investigation of services/api - did the planned signals land?
/odd-verify re-measure my last checkout report - nothing changed, is it stable?
```

- no arguments - the newest report across both `.odd/` report
  directories;
- "checkout-latency-sweep" / the full path - the baseline report;
- "my last report for checkout" / "my last prod report" - resolution
  by service or by recorded deployment environment, through the stored
  frontmatters;
- naming an instrumentation report turns the mission into presence
  rulings (planned spans, metrics, log correlation - closed or still
  missing);
- when the replay tests no fix - the code is unchanged since the
  report's `revision`, or the arguments say drift/stability re-measure
  - the run persists as a **re-measure**
  (`remeasure-<run_name>.md`, `mode: re-measure`, same `verifies`
  link), not as a verification: `/odd-status` counts it as an
  observation, never as "verified".

## /odd-status

Answers "where is the loop?" from the committed `.odd/` history and
git alone - read-only, no backend queries. Free-form arguments map to:
**service name(s)**, a **stack**, and/or a **deployment environment**
to restrict the status to.

```text
/odd-status
/odd-status where is the loop for my service checkout
/odd-status what was observed on prod for my service checkout
/odd-status status of the local stack runs only
```

## /odd-config

Displays the current backend configuration - configured stack,
targeted instance, connection proof - then offers to change it.
Free-form arguments may name a **target stack** or a **persist
request** directly.

```text
/odd-config
/odd-config switch to datadog
/odd-config persist workspace 0000-1111-2222 for azure-monitor
/odd-config clear the workspace for azure-monitor
/odd-config set the local Grafana port to 3001
```

- no arguments - display first, then the "Change backend?" choice;
- "switch to datadog" - routes straight to the backend switch (CLI
  presence checked, install offered, nothing silent);
- "persist ... for azure-monitor" - stores a non-secret targeting
  value in that stack's `stack_config`, without switching;
- "clear ... for azure-monitor" - removes a persisted value through
  the same step (a null write), without switching and without touching
  the stack container;
- port changes reset the local stack container - the command says so
  before doing it.
