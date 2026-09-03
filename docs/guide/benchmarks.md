# Benchmark authoring and running

A k6 load-test benchmark, written once as reviewed code and replayed
identically for as long as it stays useful. The contracts belong to
the [`/odd-instrument-bench`](../../.apm/prompts/odd-instrument-bench.prompt.md)
prompt, the [`k6-benchmark-expert`](../../.apm/agents/k6-benchmark-expert.agent.md)
agent, and the [`create-update-benchmark`](../../.apm/skills/create-update-benchmark/SKILL.md)
skill.

## Install k6

`k6` on your path — `brew install k6` on macOS or Linux, or the
official packages for other platforms:
https://grafana.com/docs/k6/latest/set-up/install-k6/. The prompts
check for it before dispatching and install it through Homebrew when
they can; otherwise they hand you the steps and stop.

## Author

```text
/odd-instrument-bench author a load benchmark for checkout, stress test, p95 under 300ms
```

Writes a k6 script and a manifest into `.odd/benchmarks/<name>/`. You
decide what only you can — test type, thresholds, target, new
benchmark or an update to an existing one, and whether one smoke
iteration may be sent at a remote target — and confirm the load shape
the agent proposes; which endpoints matter, it finds out itself.

Your thresholds are checked against what the service's own code can
reach: a threshold it can structurally never meet (a `p(95)<300ms` on
a handler that sleeps longer) comes back to you with the file and line
as evidence, and you raise it, drop it, re-scope it, or keep it
knowingly. Nothing is persisted until you have decided.

The agent validates what it wrote — `k6 inspect` and one smoke
iteration at the target — and records the outcome in the manifest. It
never runs the benchmark; that is `/odd-observe`'s job. An update to
an existing benchmark comes back as a reviewed diff, never a silent
replacement.

## Run

```text
/odd-observe run .odd/benchmarks/checkout-read-heavy/
/odd-observe drive the checkout-read-heavy benchmark on the local stack, focus on latency
/odd-observe someone is running checkout-read-heavy against uat right now - observe it
```

Name the benchmark in an `/odd-observe` mission, by directory or path:

- **drive**: the `observe-run` agent runs the stored script itself,
  unmodified, from a clean base — the service restarted and the local
  stack reset, so telemetry stored before the run is wiped; a base URL
  or a named secret the manifest leaves open is passed at mission time
  and recorded by name;
- **observe**: someone else runs it, the agent only watches the
  telemetry;
- **post-hoc** takes no benchmark: the agent cannot attest that the
  plan produced the window.

The report cites the benchmark by name and git revision, rules on the
manifest's thresholds from the service's own telemetry, and keeps k6's
summary as evidence only; when the k6 run itself threw, no threshold
is ruled — every row reads `void` and the defect is the report's first
finding. Driving a remote target is authorized in
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
