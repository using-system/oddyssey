---
name: run-scenario
description: Drive a reproducible request scenario against a locally running service and record it verbatim, so the telemetry it produces can be compared with a later run. Use when traffic must be generated before observing a service, when an observation report needs a replayable scenario, or when verifying after a fix that the same scenario now measures better.
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

## Output

The scenario block from step 4, ready to paste into an observation report
(the run record, and the replay instruction in the measurement protocol) —
and ready to re-run unchanged after a fix.

## Rules

- Drive the service only; never change its code or configuration to make a
  scenario nicer. If a scenario cannot run as given, report why.
- Replay after a fix with the **same** commands, counts, warmup, and
  concurrency — one changed variable invalidates the comparison.
- Same machine, same data volume, same environment where possible; if
  something differed between the two runs, say so next to the numbers.
- A failed or partial run is data: record the failures and their counts
  rather than retrying silently until the numbers look clean.
