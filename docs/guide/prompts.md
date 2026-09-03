# Prompt usage examples

Every oddyssey prompt takes free-form arguments: describe the mission
in plain words, and the prompt maps them onto the fields its agent or
skill expects. This page shows what good invocations look like and
which part of the sentence feeds which field. The contracts are the
prompts themselves, under [`.apm/prompts/`](../../.apm/prompts/); the
architecture behind them is mapped in [dependencies.md](dependencies.md).

## /odd-instrument-otel

Investigates a codebase and hands back everything needed to plan its
OpenTelemetry instrumentation, as a report under
`.odd/otel-instrumentation-reports/`. Arguments: the **path or
repository** (default: the current repository) and the **export
stack** (default: the local stack).

```text
/odd-instrument-otel add OpenTelemetry to this repository
/odd-instrument-otel my stack has no telemetry at all - start from scratch, everything exports to the local stack
/odd-instrument-otel add OpenTelemetry to services/checkout, we already emit some custom Prometheus metrics
/odd-instrument-otel migrate services/api from winston logging to OpenTelemetry logs, keep the existing log statements
/odd-instrument-otel instrument this repo for a remote Grafana stack, and plan a contrib Collector deployed via Terraform as the gateway
/odd-instrument-otel my agent under src/assistant is built on LangChain - plan GenAI observability with the gen_ai semantic conventions for its LLM calls
```

- "this repository" / "services/checkout" - the investigated path;
- "to the local stack" / "for a remote Grafana stack" - the export
  stack;
- everything else (existing telemetry, a logging library to migrate
  from, the Collector shape, a GenAI framework) is context the
  investigation verifies and turns into decisions or open questions.

## /odd-instrument-bench

Writes a k6 load-test benchmark — a script plus a manifest — under
`.odd/benchmarks/<name>/`, validated but never run as a benchmark.
Arguments: the **service** (required), **new or update**, the **test
type**, the **thresholds**, the **target** base URL or environment,
and optionally a **load shape and duration**; whatever is left open,
the prompt asks before dispatching. See
[benchmarks.md](benchmarks.md).

```text
/odd-instrument-bench author a load benchmark for checkout, p95 under 300ms
/odd-instrument-bench stress test payment against http://localhost:8080, error rate must stay under 1%
/odd-instrument-bench smoke benchmark for orders on staging, 1 VU for 1 minute
/odd-instrument-bench update the checkout-read-heavy benchmark - the cart endpoints moved
/odd-instrument-bench soak test api for 2 hours at 50 VUs, p99 under 800ms
```

- "checkout", "payment", "orders" - the service;
- "author a load benchmark" / "update the checkout-read-heavy
  benchmark" - new versus update; when ambiguous, the prompt lists
  what exists for that service and asks;
- "stress test" / "smoke benchmark" / "soak test" - the test type, one
  of k6's six;
- "p95 under 300ms" / "error rate must stay under 1%" - the
  thresholds; one the service can never meet comes back to you with
  the evidence rather than being persisted;
- "against http://localhost:8080" / "on staging" - the target; a
  remote one also gets asked whether one smoke iteration may be sent
  at it;
- "50 VUs for 2 hours" / "1 VU for 1 minute" - the load shape and
  duration; left out, the prompt proposes one for you to confirm;
- which endpoints to exercise is never an argument: the agent
  discovers them.

## /odd-observe

Observes a running service through its telemetry and writes the
plan-ready report under `.odd/observe-run-reports/`. Arguments:
**service name(s)**, **stack** (default: the configured one),
**mode** (`drive` / `observe` / `post-hoc`), **depth** (`quick` /
`full`), **benchmark**, **window**, **focus**, and **baseline
expectations**. The deployment environment is never an argument: the
agent detects it from the telemetry.

> The target stack's CLI must be configured and connected beforehand:
> the preflight proves it and fails fast, it never authenticates for
> you. `/odd-config` is the guided way to switch stacks; naming a
> stack in the mission switches too.

```text
/odd-observe check that checkout starts and answers requests on the /user endpoint
/odd-observe drive a 50-request scenario against payment on the local stack, focus on latency
/odd-observe someone is load-testing checkout right now - observe the run until I say stop
/odd-observe post-hoc: what did orders do between 14:00 and 15:00 UTC?
/odd-observe switch to grafana and observe checkout, focus on errors
/odd-observe observe checkout after my last deployment, error rate should stay under 1%
/odd-observe run .odd/benchmarks/checkout-read-heavy/
/odd-observe someone is running the checkout-read-heavy benchmark right now - observe it
/odd-observe list the services with metrics on my stack grafana over the last 30 days - just the names
/odd-observe quick check that orders answers on /health
/odd-observe full audit of checkout before the SDD wave
```

- "checkout", "payment", "orders" - the services;
- "on the local stack" / "switch to grafana" - the stack, one of the
  values in [backends.md](backends.md);
- "on prod" / "on uat" - an expectation about the deployment
  environment the agent detects, never a stack;
- "drive a ... scenario" / "observe the run" / "post-hoc" - the mode;
  a drive mission starts from a clean base: the service is restarted
  and the local stack reset, so telemetry stored before the run is
  wiped; when the service's port is already served by something the
  run did not start, the run leaves it alone and drives its own
  instance on a free port, and the report says so;
- "quick check that ..." / "full audit ..." - the depth: `quick`
  answers a one-question mission in minutes with the signals it
  needs, `full` runs the whole protocol; with no such word the prompt
  asks, `quick` recommended;
- "run .odd/benchmarks/checkout-read-heavy/" / "someone is running
  the checkout-read-heavy benchmark" - a stored benchmark, driven by
  the agent or only watched; never with `post-hoc`;
- "list the services with metrics ..." - a discovery question about
  the stack, answered directly with the query as evidence, no report;
- "between 14:00 and 15:00 UTC" / "after my last deployment" - the
  window;
- "focus on latency" / "error rate should stay under 1%" - focus and
  baseline expectations.

## /odd-verify

Replays a stored report's protocol and rules on everything it
recorded, as a new report under `.odd/observe-run-reports/`.
Arguments: the **report to verify against** (a path under `.odd/`, or
enough of a run name to find it — an observation or an instrumentation
report; default: the newest) and, on a remote stack, the **access
material** by name.

> A verify run replays the **report's** stack, never the configured
> one, so that stack's CLI must be connected beforehand.

```text
/odd-verify
/odd-verify check that report checkout-latency-sweep has been fixed
/odd-verify replay .odd/observe-run-reports/2026-08-26-1003-config-set-env-preservation.md
/odd-verify verify my last report for checkout
/odd-verify verify my last prod report
/odd-verify verify the instrumentation investigation of services/api - did the planned signals land?
/odd-verify re-measure my last checkout report - nothing changed, is it stable?
/odd-verify full verify of my last orders report
```

- no arguments - the newest stored report;
- "checkout-latency-sweep" / the full path - the baseline;
- "my last report for checkout" / "my last prod report" - resolution
  by service or by detected environment;
- an instrumentation report turns the mission into presence rulings:
  each planned signal closed, present but unattributed (nothing proves
  which process emitted it), or still missing;
- a `drive` replay on a remote stack asks you first, every time, and
  a refusal ends the mission;
- when nothing changed in the code since the report, the run is
  stored as a **re-measure** (`remeasure-<run_name>.md`), never as a
  verification; when the code state contradicts how you framed the
  mission, the prompt asks;
- "full verify" / "quick check" - the depth; otherwise it is the
  baseline report's, `quick` for a report written before the field,
  and the prompt says which before dispatching; an instrumentation
  report replays at `full`, its rulings spanning every signal.

## /odd-status

Answers "where is the loop?" from the committed `.odd/` history and
git alone — no backend query, nothing written. Arguments: **service
name(s)**, a **stack**, and/or a **deployment environment** to
restrict the picture to, or a **decision on a finding**.

```text
/odd-status
/odd-status where is the loop for my service checkout
/odd-status what was observed on prod for my service checkout
/odd-status status of the local stack runs only
/odd-status status for the service checkout-api on prod
/odd-status wontfix F4 of my last checkout report - port-move is rare, 14.5s accepted
```

- no arguments - the whole picture;
- "for my service checkout" / "on prod" / "the local stack runs" -
  the scope; a scope matching nothing says what was searched and
  what exists instead, never an error;
- "wontfix F4 of my last checkout report - ..." - a decision: the
  finding, the verdict, and a one-sentence rationale, recorded as one
  row in `.odd/decisions.md`; the finding then renders as declined,
  and "reopen F4: ..." reverses it. The prompt asks when the reference
  is ambiguous or the rationale missing.

## /odd-config

Displays the current backend configuration — stack, targeted
instance, connection proof — then offers to change it. Arguments: a
**target stack**, or a value to **persist** or **clear** for one.

```text
/odd-config
/odd-config switch to datadog
/odd-config persist workspace 0000-1111-2222 for azure-monitor
/odd-config clear the workspace for azure-monitor
/odd-config set the local Grafana port to 3001
```

- no arguments - display, then the "Change backend?" choice;
- "switch to datadog" - the guided switch: CLI presence checked,
  install offered, nothing silent;
- "persist ... for azure-monitor" / "clear ..." - a targeting value
  stored or removed without switching;
- a local port change resets the local stack container, and the
  prompt says so first.
