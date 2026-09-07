# Benchmark authoring and running

A k6 load-test benchmark, written once as reviewed code and replayed
identically for as long as it stays useful. The contracts belong to
the [`/odd-instrument-bench`](../../.apm/prompts/odd-instrument-bench.prompt.md)
prompt, the [`k6-benchmark-expert`](../../.apm/agents/k6-benchmark-expert.agent.md)
agent, and the [`benchmark`](../../.apm/skills/odd-memory/references/benchmark.md)
reference of the `odd-memory` skill.

## Install k6

`k6` on your path — `brew install k6` on macOS or Linux, or the
official packages for other platforms:
https://grafana.com/docs/k6/latest/set-up/install-k6/. The prompts
check for it before dispatching and install it through Homebrew when
they can; otherwise they hand you the steps and stop.

## Author

```text
/odd-instrument-bench author a benchmark for checkout, stress test, p95 under 300ms
```

Writes a k6 script and a manifest into `.odd/benchmarks/<name>/`. You
decide what only you can — test type, thresholds, target, new
benchmark or an update to an existing one, and whether one smoke
iteration may be sent at a remote target — and confirm the load shape
the prompt proposes; which endpoints matter, the agent finds out
itself.

Your thresholds are checked against what the service's own code can
reach: a threshold it can structurally never meet (a `p(95)<300ms` on
a handler that sleeps longer) comes back to you with the file and line
as evidence, and you raise it, drop it, re-scope it, or keep it
knowingly. So does one whose expression does not say what you meant —
`rate>0.99` stops meaning "no check may fail" as soon as a run
performs more than a hundred checks — with the arithmetic as the
evidence. Nothing is persisted until you have decided.

The agent validates what it wrote — `k6 inspect` and one smoke
iteration at the target — and records the outcome in the manifest. It
never runs the benchmark; that is `/odd-observe`'s job. An update to
an existing benchmark comes back as a reviewed diff, never a silent
replacement.

### Which benchmark to author


The type is yours to decide: it encodes what you want to learn, and
nothing in the code can answer that for you. Six exist, one question
each. Name it in the invocation, with the thresholds that matter; the
prompt proposes a load shape that fits the type and you confirm it.

**Smoke** — does the service work at all under minimal load? One or
two virtual users for a minute, the first benchmark of a service that
has none.

```text
/odd-instrument-bench smoke benchmark for orders on staging, 1 VU for 1 minute
```

No threshold named, so the prompt asks which pass/fail targets
matter; "on staging" is a remote target, so it also asks whether one
smoke iteration may be sent there before the benchmark is stored.

**Average-load** ("load" in an invocation) — how does the service
behave under its everyday traffic? Steady virtual users at the
expected concurrency, held for a while.

```text
/odd-instrument-bench load benchmark for checkout at 20 VUs for 10 minutes, p95 under 300ms
```

**Stress** — where does the service start to degrade above its normal
traffic? Virtual users ramp beyond the expected load until latency or
errors climb; the prompt proposes how high and how fast.

```text
/odd-instrument-bench stress test payment against http://localhost:8080, error rate must stay under 1%
```

**Soak** — does the service degrade over a long run: leaks, resource
exhaustion, slow drift? Moderate, steady load held for hours, so run
it when the service and the stack can be left alone that long.

```text
/odd-instrument-bench soak test api for 2 hours at 50 VUs, p99 under 800ms
```

**Spike** — does the service survive a sudden, sharp burst, and come
back once it passes? A fast ramp to a high count, a brief hold, a
fast ramp down.

```text
/odd-instrument-bench spike benchmark for payment, burst to 200 VUs for 30 seconds, no request may fail
```

**Breakpoint** — what is the service's actual capacity ceiling? Load
increases continuously until the service breaks; the threshold names
the point past which it counts as broken.

```text
/odd-instrument-bench breakpoint benchmark for checkout against http://localhost:8080, p95 under 1s
```

An invocation that names no type is asked which one. The shape and
the thresholds you decided end up in the manifest, so a later run
replays exactly that.

## Run

```text
/odd-observe run .odd/benchmarks/checkout-read-heavy/
/odd-observe drive the checkout-read-heavy benchmark on the local stack, focus on latency
/odd-observe someone is running checkout-read-heavy against uat right now - observe it
```

Name the benchmark in an `/odd-observe` mission, by directory or path:

- **drive**: the `observe-run` agent runs the stored script itself,
  unmodified, from a clean base — the service restarted with this run's
  own identity, so the run is separated from whatever the stack already
  held; wiping the stack is a separate decision the agent takes only
  when the mission needs an empty store, and it says so. A base URL
  or a named secret the manifest leaves open is passed at mission time
  and recorded by name;
- **observe**: someone else runs it, the agent only watches the
  telemetry — it watches for the run's own requests rather than
  trusting the start time you announced, reports the run's span rather
  than the time it spent waiting, and writes one report per watching
  mission, named for the run and the backend it watched from;
- **post-hoc** takes no benchmark: the agent cannot attest that the
  plan produced the window.

The report cites the benchmark by name and git revision, rules on the
manifest's thresholds from the service's own telemetry, and keeps k6's
summary as evidence only; when the k6 run itself threw, no threshold
is ruled — every row reads `void` and the defect is the report's first
finding. An observed run has no k6 output of its own to keep: the
agent quotes the driver's when you hand it over, and otherwise says so
in the report and rules the thresholds from the telemetry alone — it
voids a ruling where the benchmark's own plan makes a shortfall
provable, and reports the gap as a finding where that plan leaves it
unprovable. Driving a remote target is authorized in
the prompt, every run.

## Verify

`/odd-verify` replays a benchmark-backed report in the mode the report
records — an observed run is never re-driven — and asks first before
driving a remote stack. A benchmark is living source: a change to its
script or manifest makes the next replay a verification of that
change, and the report says whether the service's before/after numbers
still compare (same requests, pacing, and stages) or open a new
baseline. Checking the benchmark out at the recorded revision instead
of `HEAD` is designed, not built yet.
