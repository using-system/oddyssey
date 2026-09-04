# Prompt usage examples

Every oddyssey prompt takes free-form arguments: describe the mission
in plain words, and the prompt maps them onto the fields its agent or
skill expects. This page shows what good invocations look like and
which part of the sentence feeds which field: each example is followed
by its own mapping, and the notes that hold for a prompt as a whole
come after its examples. The contracts are the prompts themselves,
under [`.apm/prompts/`](../../.apm/prompts/); the architecture behind
them is mapped in [dependencies.md](dependencies.md).

## /odd-instrument-otel

Investigates a codebase and hands back everything needed to plan its
OpenTelemetry instrumentation, as a report under
`.odd/otel-instrumentation-reports/`. Arguments: the **path or
repository** (default: the current repository) and the **export
stack** (default: the local stack).

```text
/odd-instrument-otel add OpenTelemetry to this repository
```

"this repository" is the investigated path; no stack named, so the
export stack is the local one.

```text
/odd-instrument-otel my stack has no telemetry at all - start from scratch, everything exports to the local stack
```

"everything exports to the local stack" is the export stack; "no
telemetry at all" is context the investigation verifies.

```text
/odd-instrument-otel add OpenTelemetry to services/checkout, we already emit some custom Prometheus metrics
```

"services/checkout" is the investigated path; the existing Prometheus
metrics are context the investigation verifies and turns into
decisions or open questions.

```text
/odd-instrument-otel migrate services/api from winston logging to OpenTelemetry logs, keep the existing log statements
```

"services/api" is the investigated path; the logging library to
migrate from, and the wish to keep its statements, are context that
becomes decisions or open questions.

```text
/odd-instrument-otel instrument this repo for a remote Grafana stack, and plan a contrib Collector deployed via Terraform as the gateway
```

"this repo" is the investigated path, "for a remote Grafana stack"
the export stack; the Collector shape is context that becomes
decisions or open questions.

```text
/odd-instrument-otel my agent under src/assistant is built on LangChain - plan GenAI observability with the gen_ai semantic conventions for its LLM calls
```

"src/assistant" is the investigated path; the GenAI framework and the
semantic conventions to apply are context the investigation verifies.

Across all of them:

- whatever is not a path or a stack - existing telemetry, a library
  to migrate from, a Collector shape, a framework - is context: the
  investigation verifies it and turns it into decisions or open
  questions.

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
```

"checkout" is the service, "author" makes it a new benchmark, "load"
the test type, "p95 under 300ms" the threshold; no target and no load
shape, so the prompt asks for the target and proposes a load shape for
you to confirm.

```text
/odd-instrument-bench stress test payment against http://localhost:8080, error rate must stay under 1%
```

"payment" is the service, "stress test" the test type, "against
http://localhost:8080" the target, "error rate must stay under 1%"
the threshold.

```text
/odd-instrument-bench smoke benchmark for orders on staging, 1 VU for 1 minute
```

"orders" is the service, "smoke" the test type, "on staging" the
target - a remote one, so the prompt also asks whether one smoke
iteration may be sent at it - and "1 VU for 1 minute" the load shape
and duration.

```text
/odd-instrument-bench update the checkout-read-heavy benchmark - the cart endpoints moved
```

"update the checkout-read-heavy benchmark" names an existing benchmark
to update rather than a new one; the rest is context passed on to the
authoring agent.

```text
/odd-instrument-bench soak test api for 2 hours at 50 VUs, p99 under 800ms
```

"api" is the service, "soak test" the test type, "2 hours at 50 VUs"
the load shape and duration, "p99 under 800ms" the threshold.

Across all of them:

- the test type is one of k6's six;
- new versus update: when ambiguous, the prompt lists what exists for
  that service and asks;
- a threshold the service can never meet comes back to you with the
  evidence rather than being persisted;
- a load shape left out is proposed by the prompt for you to confirm;
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

> The target stack's CLI must be installed, configured and connected
> beforehand: the preflight proves it and fails fast — offering the
> install when the binary is missing — and never authenticates for
> you. `/odd-config` is the guided way to switch stacks; naming a
> stack in the mission switches too.

```text
/odd-observe check that checkout starts and answers requests on the /user endpoint
```

"checkout" is the service, "the /user endpoint" the focus; no stack
named, so the configured one.

```text
/odd-observe drive a 50-request scenario against payment on the local stack, focus on latency
```

"payment" is the service, "drive a ... scenario" the `drive` mode,
"on the local stack" the stack, "focus on latency" the focus.

```text
/odd-observe someone is load-testing checkout right now - observe the run until I say stop
```

"checkout" is the service, "observe the run" the `observe` mode: the
agent watches traffic it did not start; "until I say stop" bounds the
window at your word.

```text
/odd-observe post-hoc: what did orders do between 14:00 and 15:00 UTC?
```

"orders" is the service, "post-hoc" the mode, "between 14:00 and
15:00 UTC" the window.

```text
/odd-observe switch to grafana and observe checkout, focus on errors
```

"switch to grafana" is the stack - naming one switches the
configuration, one of the values in [backends.md](backends.md) -
"checkout" the service, "focus on errors" the focus.

```text
/odd-observe observe checkout after my last deployment, error rate should stay under 1%
```

"checkout" is the service, "after my last deployment" the window,
"error rate should stay under 1%" a baseline expectation.

```text
/odd-observe run .odd/benchmarks/checkout-read-heavy/
```

The path is a stored benchmark the agent drives; the service is the
one the benchmark belongs to.

```text
/odd-observe someone is running the checkout-read-heavy benchmark right now - observe it
```

"the checkout-read-heavy benchmark" is a stored benchmark, "observe
it" the `observe` mode: the benchmark is only watched, never driven by
the agent.

```text
/odd-observe list the services with metrics on my stack grafana over the last 30 days - just the names
```

A discovery question about the stack, "my stack grafana", over the
window "the last 30 days": answered directly with the query as
evidence, no report written.

```text
/odd-observe quick check that orders answers on /health
```

"orders" is the service, "quick check" the `quick` depth: a
one-question mission answered in minutes with the signals it needs,
"/health" the focus.

```text
/odd-observe full audit of checkout before the SDD wave
```

"checkout" is the service, "full audit" the `full` depth: the whole
protocol runs.

Across all of them:

- "on prod" / "on uat" is an expectation about the deployment
  environment the agent detects, never a stack;
- a `drive` mission starts from a clean base: the service is
  restarted and the local stack reset, so telemetry stored before the
  run is wiped; when the service's port is already served by
  something the run did not start, the run leaves it alone and drives
  its own instance on a free port, and the report says so;
- with no depth word the prompt asks, `quick` recommended;
- a stored benchmark is never combined with `post-hoc`.

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
```

No arguments: the newest stored report is the baseline.

```text
/odd-verify check that report checkout-latency-sweep has been fixed
```

"checkout-latency-sweep" is enough of a run name to find the baseline
report.

```text
/odd-verify replay .odd/observe-run-reports/2026-08-26-1003-config-set-env-preservation.md
```

The full path is the baseline report.

```text
/odd-verify verify my last report for checkout
```

"my last report for checkout" resolves the baseline by service: the
newest report on checkout.

```text
/odd-verify verify my last prod report
```

"my last prod report" resolves the baseline by detected deployment
environment: the newest report whose run was detected on prod.

```text
/odd-verify verify the instrumentation investigation of services/api - did the planned signals land?
```

"the instrumentation investigation of services/api" is an
instrumentation report as the baseline: the mission turns into
presence rulings - each planned signal closed, present but
unattributed (nothing proves which process emitted it), or still
missing - and replays at `full`, its rulings spanning every signal.

```text
/odd-verify re-measure my last checkout report - nothing changed, is it stable?
```

"my last checkout report" is the baseline; "nothing changed" is how
you framed it: the prompt checks the code state and, when it agrees,
stores the run as `remeasure-<run_name>.md`, never as a verification.

```text
/odd-verify full verify of my last orders report
```

"my last orders report" is the baseline, "full verify" the depth,
overriding the baseline report's.

Across all of them:

- a `drive` replay on a remote stack asks you first, every time, and
  a refusal ends the mission;
- when nothing changed in the code since the report, the run is
  stored as a re-measure whatever the wording; when the code state
  contradicts how you framed the mission, the prompt asks;
- "full verify" / "quick check" sets the depth; otherwise it is the
  baseline report's, `quick` for a report written before the field,
  and the prompt says which before dispatching.

## /odd-status

Answers "where is the loop?" from the committed `.odd/` history and
git alone — no backend query, nothing written. Arguments: **service
name(s)**, a **stack**, and/or a **deployment environment** to
restrict the picture to, or a **decision on a finding**.

```text
/odd-status
```

No arguments: the whole picture.

```text
/odd-status where is the loop for my service checkout
```

"my service checkout" restricts the picture to one service.

```text
/odd-status what was observed on prod for my service checkout
```

"on prod" restricts it to one detected deployment environment, "my
service checkout" to one service.

```text
/odd-status status of the local stack runs only
```

"the local stack runs" restricts it to one stack.

```text
/odd-status status for the service checkout-api on prod
```

"checkout-api" is the service, "on prod" the deployment environment.

```text
/odd-status wontfix F4 of my last checkout report - port-move is rare, 14.5s accepted
```

A decision on a finding: "F4 of my last checkout report" is the
finding, "wontfix" the verdict, the rest a one-sentence rationale,
recorded as one row in `.odd/decisions.md`; the finding then renders
as declined, and "reopen F4: ..." reverses it.

Across all of them:

- a scope matching nothing says what was searched and what exists
  instead, never an error;
- for a decision, the prompt asks when the finding reference is
  ambiguous or the rationale missing.

## /odd-config

Displays the current backend configuration — stack, targeted
instance, connection proof — then offers to change it. Arguments: a
**target stack**, a value to **persist** or **clear** for one, or a
**custom stack to create or complete** for a backend the package does
not ship.

```text
/odd-config
```

No arguments: display, then the "Change backend?" choice.

```text
/odd-config switch to datadog
```

"switch to datadog" is the target stack: the guided switch, CLI
presence checked, install offered, nothing silent.

```text
/odd-config persist workspace 0000-1111-2222 for azure-monitor
```

"persist workspace ... for azure-monitor" is a targeting value stored
for that stack, without switching to it.

```text
/odd-config clear the workspace for azure-monitor
```

"clear the workspace for azure-monitor" removes that targeting value,
without switching.

```text
/odd-config set the local Grafana port to 3001
```

A local port change: it resets the local stack container, and the
prompt says so first.

```text
/odd-config create a stack seq
/odd-config create a stack seq from https://datalust.co/docs/command-line-client
/odd-config create a stack seq from ./docs/seq/ : query it with seqcli, the connection is set with seqcli config, no profiling
```

"create a stack seq" is the custom stack to create — `seq` becomes
`.odd/observability-stacks/seq.md`; "from <URL or path>" is the
documentation to read first, and what follows the colon is your own
instructions, written in as told; the web fills what those left open.
The file is checked against the reference contract, committed, and the
switch to it offered.

```text
/odd-config create a stack seq linked to https://github.com/example-org/obs-guides stacks/seq.md
```

"linked to <repository and path>" (or a URL) writes only a pointer to a
guide another repository carries — one guide for the whole team; the
switch fetches and checks it every time.

```text
/odd-config for stack seq: the traces endpoint is /api/traces, it takes a service query parameter
```

"for stack seq: ..." completes an existing custom stack file: the
instruction becomes a diff to the section it touches, shown before it
is committed — or, for a linked guide, proposed as a pull request on
the repository that carries it, or shown for you to apply there. A
built-in stack is refused here — it changes through the package.

```text
/odd-config switch to seq
```

"switch to seq" names a custom stack the repository carries: the same
guided switch, with the file checked against the contract first.
