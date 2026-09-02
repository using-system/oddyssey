---
name: run-scenario
description: Drive a reproducible request scenario against a locally running service - ad-hoc requests, or a stored k6 benchmark from .odd/benchmarks/ - and record it verbatim, so the telemetry it produces can be compared with a later run. Use when traffic must be generated before observing a service, when a stored k6 benchmark must be run, when an observation report needs a replayable scenario, or when verifying after a fix that the same scenario now measures better.
---

# Run a Scenario

One protocol on both ends of the ODD loop: the same commands that produced
the numbers in an observation report produce the numbers that verify the
fix. A scenario that cannot be replayed verbatim makes before/after
comparison an impression, not a measurement.

## 0. A clean backend is not a clean run

`odd_stack_reset` clears the **store**, not the **process**: cumulative
counters and histograms live in the application and keep their pre-run
history, while traces and logs are window-scoped — the two signal
families disagree about what "the run" is. Restart order matters too: an
old process that outlives the reset flushes its whole cumulative history
into the brand-new store on its next periodic export.

Start a clean run in this order — the reverse of what feels natural:

1. **Restart the observed process first** — its dying flush lands in the
   old store;
2. **then `odd_stack_reset`** — the wipe takes that flush with it;
3. record the new process's identity in the protocol —
   `service.instance.id` when the SDK emits one, or the backend
   equivalent when it is absent (its start time, a
   `target_info` label, a container id) — and qualify every
   cumulative-metric query with it: an unfiltered query mixes instances
   the moment an old one got a last export in.

   **Prefer creating the identity over hunting for a substitute.** When
   the driven service honors `OTEL_RESOURCE_ATTRIBUTES` — any OTel SDK
   service, including `oddyssey-mcp`, which strips the SDK's default
   UUID unless opted in — launch its process with
   `OTEL_RESOURCE_ATTRIBUTES=service.instance.id=<run slug>` and record
   the slug you chose. One bounded label per run makes the run's
   cumulative series attributable by name and keeps a co-resident
   server's re-exported history (an installed `uvx oddyssey-mcp`
   long-lived process dumps its whole counter history into a
   seconds-old store) separable instead of merely suspected. The
   substitutes above stay the fallback for services that cannot opt in.

When restarting is not possible, say so in the record — and still record
the identity **and the process start time**: the start time is what
dates the pre-window history. Traces and logs stay trustworthy, but
cumulative metrics read inside the window include pre-window activity —
treat them as deltas between the window's edges, never as run totals
(valid only within one instance, which the recorded identity proves).

**When a reset is forbidden** — not impossible, actively harmful: a
creation-time env the reset would not reapply (credential-named
variables are never persisted — `env_not_persisted` names them — and a
manually run or pre-persistence container has nothing recorded to
reapply), or shared stored
history the caller still needs — do not take the clean slate at all.
Isolate the window without one: **time-scope every query explicitly**
to the recorded start/end (no unscoped search, no store-equals-run
shortcut), qualify every cumulative-metric query with the recorded
identity and read it as a window-edge delta, and say in the record
that the run rode a shared store and why the reset was off the table.
A window carved by timestamps out of a live store is a weaker
isolation than a wipe — the record must let the verify run reproduce
the same carving.

## 1. Decide what to exercise

In order of preference:

1. **The caller's list** — endpoints, payloads, and counts given in the
   mission. Use them as-is; do not "improve" them.
2. **Traces already in the stack** — the operations Tempo has seen for this
   service (`gcx traces query` on `{resource.service.name="<svc>"}`, group by
   span name) are what the service actually serves. Configure gcx against
   the local stack with the `setup-local-stack` skill first.
3. **The service's own contract** — an OpenAPI/Swagger document, a route
   table, a CLI entry point in the repository (read-only).

Prefer a handful of representative operations covered properly over every
endpoint covered once. Note anything you deliberately left out.

## 2. Warm up

Send a few requests per endpoint (typically 5) before measuring: JIT
compilation, connection pools, lazy caches, and first-hit schema loads all
land in the first requests and distort a small sample. Discard the warmup
from the quoted numbers, and say in the record that it was discarded —
unless an iteration is expensive: see the carve-out in step 3.

## 3. Iterate enough to quote a number

- **>= 30 requests per endpoint** before quoting a p95. Below that, report
  observations, not quantiles.
- **~100** before quoting a p99.
- Sequential by default. If concurrency is part of the question, state the
  level explicitly — it changes every latency number.
- Keep inputs deterministic: fixed IDs, fixed payloads, a fixed seed. A
  random payload is not replayable; if randomness is unavoidable, record the
  seed.

### When an iteration is expensive or non-deterministic

The counts above assume cheap, repeatable iterations. Some scenarios are
neither: an LLM-backed job can cost real money and tens of minutes per
iteration, and two identical invocations legitimately differ (turn
count, tool mix, tokens, duration). Then:

- **How many samples to spend is the caller's decision, not yours** —
  state the count in the record and run that. When the mission names no
  count and an iteration is visibly expensive, stop after the first
  sample and ask: a sample spent is a decision the caller never made.
  Skipping the warmup is expected at these prices: keep the first
  sample and mark it cold instead of discarding it.
- **Never dress samples up as statistics** — quote every number with its
  sample count (`n=2`), and at one or two samples write *observation*,
  never a quantile or a mean. A verify run that diffs two single
  observations is comparing noise.
- **Non-deterministic runs are compared by structure and order of
  magnitude** — same steps present, similar proportions, durations and
  costs in the same range — never value against value. Record what varied
  between identical invocations, so the verify run knows what noise
  looks like.

### Waiting out the scenario — inside the turn, never past it

A scenario that fits a tool call's budget (hosts allow up to ~10
minutes) runs as **one blocking foreground command** that drives the
requests and exits when the last one is done — never as a background
job plus a poll loop. When the platform blocks foreground `sleep`, use
its blocking wait primitive (a Monitor-style until-condition tool)
instead of pushing the wait itself into the background (the scenario
may then have to run as a background job — the wait never does). Never
end the turn to "wait for a completion notification": as a subagent —
the nominal case — ending the turn terminates the mission, the
scenario keeps running orphaned, and the waiting sentence becomes the
final result (only a main conversation is re-invoked when a background
task finishes).

### Scenarios longer than a tool call

A job running 15–30 minutes cannot be polled inside a single tool call
on hosts with a hard tool timeout (some enforce ~10 minutes): the call
dies mid-wait and takes its observations with it. The working shape is
a **detached poller**: start the job, then launch a small script with
`nohup` (survives the tool call that spawned it) that polls the job and
appends timestamped progress to a file; later tool calls only read that
file. The scenario record cites the poller script and its output file
verbatim — they are part of the protocol, and a replay re-runs the same
poller, not a hand-watched approximation.

## 4. Record verbatim

Record the scenario while running it, not from memory. The record is the
deliverable:

```text
Scenario: <name>
Base URL: http://localhost:<port>
Backend:  odd_stack_reset, env: {"PROMETHEUS_EXTRA_ARGS": "..."}   # or "defaults"
Instance: af6070... (restarted before reset)   # or equivalent identity; add the start time when not restarted
Warmup:   5 requests per endpoint (discarded)
Load:     30 requests per endpoint, sequential
Started (UTC): 2026-08-17T10:04:12Z
Ended   (UTC): 2026-08-17T10:05:03Z
Commands:
  for i in $(seq 1 30); do curl -s -o /dev/null http://localhost:8080/api/users; done
  for i in $(seq 1 30); do curl -s -o /dev/null http://localhost:8080/api/orders/42; done
Not reproducible: <auth token / seeded data / time-dependent input, or "none">
```

Exact commands, exact counts, exact UTC start and end — the start/end pair
is also the observation window for every query run against this scenario.
The `Backend:` line records how the stack was (re)started, **including any
`env`**: a replay must reproduce the backend and not only the requests. A
bare `odd_stack_reset` reapplies the env persisted in `stack_config.local`,
so most of that configuration survives on its own; only credential-named
variables — the ones the reset result lists under `env_not_persisted` — are
never stored and must be passed again on the replay.

## 5. Wait for the flush

Telemetry lags the last request. Before querying:

- **~10 s** for metrics to be exported and written into Prometheus (the stack is push-based);
- **~60 s** for traces to become searchable in Tempo (a full trace fetch by
  ID may work before search does — cross-check a suspicious search result
  against a fetch).

Only then read the window recorded in step 4.

## 6. Replay a stored k6 benchmark

When the mission names a benchmark under `.odd/benchmarks/<name>/`
(`k6-benchmark-expert` authored it, `create-update-benchmark` stored it),
the load comes from its script instead of a curl loop. Steps 0, 3 and
5 apply unchanged — the clean-base order, the sample-count rules, the
flush wait — and step 4 applies with the record shape below. What
differs is how the load is generated and how the record cites it:

- **Confirm k6 is installed before anything else — before step 0.**
  `command -v k6`, per the `k6-guides` skill's `install.md`. When it is
  absent, stop and report with that reference's install steps, with the
  observed process and the store untouched: never restart or reset for
  a run you cannot perform, never approximate the script with a curl
  loop, never install silently. `running-tests.md` in the same skill
  carries the flags, the output surface, and the exit codes cited
  below.
- **Read the manifest, then run the script unmodified.** The benchmark
  directory holds one k6 script and one manifest
  (`create-update-benchmark`'s layout): the script is `script.js`
  unless the manifest names another file. Run it from the repository
  root, as one blocking foreground command (or the detached poller
  below when the run outlasts a tool call), with k6's end-of-test
  summary exported to a scratch file:

  ```text
  k6 run .odd/benchmarks/<name>/script.js --summary-export <summary-file>
  ```

  Inputs the manifest leaves to mission time (a base URL, a named
  environment variable) are passed through k6's `-e KEY=value` or the
  environment, and recorded by name — a credential's value never lands
  in the record. Never edit the script or the manifest to make the run
  nicer: a benchmark that cannot run as stored is a reported failure,
  and a change to it goes through `/odd-instrument-bench`'s reviewed
  diff, never through the run.
- **The record cites the benchmark by name and git revision, not by
  commands.** Record the repository revision (`git rev-parse HEAD`) and
  whether the benchmark's directory is clean
  (`git status --porcelain .odd/benchmarks/<name>/` prints nothing). A
  dirty benchmark has no revision to replay at — say so in the record.
  A replay runs the same benchmark at the same revision; when the
  stored benchmark moved between the two runs (a diff-reviewed update
  landed), the protocol changed and the second run is a new baseline,
  stated as such — never a verdict on a fix.
- **Warmup is the manifest's stage boundaries.** A k6 run is one
  continuous window, so step 2's "discard the warmup" becomes a
  sub-window: quote steady-state numbers from the interval the
  manifest's ramp and steady stages delimit, record those boundaries
  as UTC timestamps, and say the ramp was excluded. Step 3's standard
  sample counts apply (>= 30 requests before a p95, ~100 before a p99)
  — k6 load is cheap, high-volume, and deterministic, so the
  expensive-iteration carve-out does not.
- **k6's own summary and exit status are evidence, never the verdict.**
  Record the exit code (`0` every threshold passed, `99` a threshold
  was crossed, anything else a setup or script error — read stderr),
  the request count, failed checks, dropped iterations, and script
  exceptions from stderr — folded into the record's `k6:` line, which
  is what survives. The summary file itself is transient: write it to
  a scratch location, never inside `.odd/benchmarks/<name>/` (it would
  dirty the directory the record just declared clean), and never
  count on it existing when the run is verified later. Then measure
  through the service's own telemetry, after step 5's flush wait. A
  generator that never connected, crashed mid-run, or threw on every
  iteration leaves telemetry that looks deceptively clean — "a failed
  or partial run is data" applies to the generator too. The manifest's
  thresholds are what the observation rules on, each against a
  telemetry-derived measurement carrying its query — **unless the
  generator threw**: script exceptions above zero mean the benchmark
  did not exercise what it was built to measure, every threshold
  ruling is void, and the run is reported as a defective benchmark (a
  finding against the script, to fix through `/odd-instrument-bench`),
  never as a pass.
- **k6's own OpenTelemetry output is a bonus signal.** Against the local
  stack, `K6_OTEL_GRPC_EXPORTER_INSECURE=true k6 run -o opentelemetry
  <script>` lands k6's client-side view in the same store under
  `service_name="k6"` (`running-tests.md`): cross-confirm against it
  when it lands, never require it, never mistake it for the target
  service.
- **A run longer than a tool call uses step 3's detached poller.** A
  staged benchmark routinely exceeds one tool call's budget; the poller
  script and its output file are part of the record.
- **This skill stays scoped to locally running services.** Whether a
  benchmark may be driven at a remote target is the observation
  caller's decision, given at mission time through `observe-run`'s own
  rule — never read from the manifest, never decided here.

The record replaces step 4's `Commands:` lines with the benchmark's
identity, the single command, and k6's own evidence:

```text
Scenario:  benchmark orders-read-heavy
Benchmark: .odd/benchmarks/orders-read-heavy/ @ 3ccfd18 (clean)
Base URL:  http://localhost:8080   # BASE_URL, mission-time
Backend:   odd_stack_reset, env: defaults
Instance:  orders-run-0902 (restarted before reset)
Stages (UTC): ramp 10:04:12–10:05:12 (excluded), steady 10:05:12–10:10:12, ramp-down 10:10:12–10:10:42
Started (UTC): 2026-09-02T10:04:12Z
Ended   (UTC): 2026-09-02T10:10:42Z
Command:
  K6_OTEL_GRPC_EXPORTER_INSECURE=true k6 run .odd/benchmarks/orders-read-heavy/script.js -o opentelemetry --summary-export /tmp/k6-summary-orders-run-0902.json -e BASE_URL=http://localhost:8080   # -o opentelemetry and its env: local stack only
k6:        exit 0, 1234 requests, checks 100%, dropped iterations 0, script errors 0 (summary file transient, numbers above are the record)
Not reproducible: none
```

## Output

The scenario block from step 4 (or step 6 for a stored benchmark), ready
to paste into an observation report (the run record, and the replay
instruction in the measurement protocol) — and ready to re-run unchanged
after a fix.

## Rules

- Drive the service only; never change its code or configuration to make a
  scenario nicer. If a scenario cannot run as given, report why.
- Replay after a fix with the **same** commands, counts, warmup, and
  concurrency — one changed variable invalidates the comparison.
- Same machine, same data volume, same environment where possible; if
  something differed between the two runs, say so next to the numbers.
- A failed or partial run is data: record the failures and their counts
  rather than retrying silently until the numbers look clean.
