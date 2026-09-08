---
name: run-scenario
description: Drive a reproducible request scenario against a locally running service - ad-hoc requests, or a stored k6 benchmark from .odd/benchmarks/ - and record it verbatim, so the telemetry it produces can be compared with a later run. Use when traffic must be generated before observing a service, when a stored k6 benchmark must be run, when an observation report needs a replayable scenario, or when verifying after a fix that the same scenario now measures better.
---

# Run a Scenario

One protocol on both ends of the ODD loop: the same commands that produced
the numbers in an observation report produce the numbers that verify the
fix. A scenario that cannot be replayed verbatim makes before/after
comparison an impression, not a measurement.

**A step this package ships a script for is run, never rewritten.** The
replay of a stored benchmark is `k6-guides`' script; the machine
preflight and the service probe are their own skills'. Authoring a shell
script that redoes one of them costs turns before it runs and yields a
different command each time — two runs then measure two things.


## Read by situation

**The two mechanical parts are scripts, not prose.** Replaying a stored
benchmark is `scripts/replay_benchmark.py` (see
[`references/benchmark-replay.md`](references/benchmark-replay.md)), and
pointing the query CLI at the local stack is the `setup-local-stack`
skill's — its `## Configure an isolated context` ships it as one
command. Run them; do not rebuild them. What is left in these files is
what you have to decide, which is the only part worth reading.

This file is the method every scenario follows — steps 1 to 5 and the
rules. What depends on the situation lives in a reference, read by the
block that applies, never whole:

| Situation | Reference |
| --- | --- |
| Every drive: the clean-base order and the identity the queries are qualified by, and the run's t0 after the warmup — a process the run launches, a port already served, a remote target the run cannot launch, a reset that is forbidden, a run whose stages are carved from timestamps | [references/run-identity.md](references/run-identity.md), the block that applies |
| An iteration that is expensive or non-deterministic, a wait that must stay inside the turn, an **ad-hoc** scenario longer than a tool call (a stored benchmark's own replay script detaches for you - see the row below) | [references/long-scenarios.md](references/long-scenarios.md) |
| A stored k6 benchmark under `.odd/benchmarks/<name>/` — driven here, or driven elsewhere and only watched | [references/benchmark-replay.md](references/benchmark-replay.md), in place of the ad-hoc commands; its watching section for a run someone else drives |

Start with the identity reference, then follow the steps below.

## 1. Decide what to exercise

In order of preference:

1. **The caller's list** — endpoints, payloads, and counts given in the
   mission. Use them as-is; do not "improve" them.
2. **Traces already in the stack** — the operations the stack's traces
   name for this service are what the service actually serves: the
   service probe (the `setup-local-stack` skill's) and the backend
   reference's discovery script both list them — read that output
   rather than querying again.
3. **The service's own contract** — an OpenAPI/Swagger document, a route
   table, a CLI entry point in the repository (read-only).

Prefer a handful of representative operations covered properly over every
operation covered once. Note anything you deliberately left out.

## 2. Warm up

Send a few requests per operation (typically 5) before measuring: JIT
compilation, connection pools, lazy caches, and first-hit schema loads all
land in the first requests and distort a small sample. Discard the warmup
from the quoted numbers, and say in the record that it was discarded —
unless an iteration is expensive: see `references/long-scenarios.md`.

## 3. Iterate enough to quote a number

- **>= 30 requests per operation** before quoting a p95 — an operation
  being the unit the service serves distinctly: on an HTTP server the
  method and the route together, so two verbs sharing a route need the
  count each, and elsewhere that surface's own unit (an RPC method, a
  tool call). Below that, report observations, not quantiles.
- **~100** before quoting a p99.
- Sequential by default. If concurrency is part of the question, state the
  level explicitly — it changes every latency number.
- Keep inputs deterministic: fixed IDs, fixed payloads, a fixed seed. A
  random payload is not replayable; if randomness is unavoidable, record the
  seed.

## 4. Record verbatim

Record the scenario while running it, not from memory. The record is the
deliverable:

```text
Scenario: <name>
Base URL: http://127.0.0.1:<port>   # not localhost: a dual-stack host may resolve it to another listener
Listeners: none   # or: :8000 served by 41234 uvicorn (127.0.0.1) and 51022 com.docker (*), ran on :8001
Backend:  odd_stack_reset, env: {"PROMETHEUS_EXTRA_ARGS": "..."}   # or "defaults"
Instance: af6070... (restarted before reset)   # or equivalent identity; add the start time when not restarted
Identity: launched with service.instance.id=<slug>   # or, when the run launched nothing: User-Agent "odd-verify/<slug>" (+ "-warmup"); traceparent "00-<prefix><run8><seq:016x>-<seq:016x>-01", run8 = sha256(<slug>)[:8]; instance read from the rows: <id>
Warmup:   5 requests per operation (discarded)
Load:     30 requests per operation, sequential
Started (UTC): 2026-08-17T10:04:12Z
Ended   (UTC): 2026-08-17T10:05:03Z
Query points: 1 (after Ended)   # more than one only with a reason - see step 5
Commands:
  for i in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:8080/api/users; done
  for i in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:8080/api/orders/42; done
  # a mission-required reset is a Commands line too (references/run-identity.md), e.g.:
  # odd_stack_reset env={"GF_LOG_LEVEL":"debug"}   # reason: the mission observes the reset itself
Not reproducible: <auth token / seeded data / time-dependent input, or "none">
```

Exact commands, exact counts, exact UTC start and end — the start/end pair
is also the observation window for every query run against this scenario.
The `Query points:` line is the default `1` — the whole scenario, then one
flush wait, then every query (step 5); a mission that must read the store
at several points lists them here with the reason each one exists. A
reset the mission requires (`references/run-identity.md`) is a `Commands:` line like any other
driven call, with its env and its reason — in a benchmark record
(`references/benchmark-replay.md`) it keeps that slot next to the single `k6 run` command.
The `Backend:` line records how the stack was (re)started, **including any
`env`**: a replay must reproduce the backend and not only the requests. A
bare `odd_stack_reset` reapplies the env persisted in `stack_config.local`,
so most of that configuration survives on its own; only credential-named
variables — the ones the reset result lists under `env_not_persisted` — are
never stored and must be passed again on the replay.

## 5. Wait for the flush — once per query point

Telemetry lags the last request. On the local stack:

- **~10 s** for metrics to be exported and written into the metrics store (the stack is push-based);
- **~60 s** for traces to become searchable in the trace store (a full
  trace fetch by ID may work before search does — cross-check a suspicious
  search result against a fetch).

**The wait is paid once per query point, after the last request that
point reads — never once per query, never once per request batch.**
The default mission has exactly one point, after `Ended`: drive the
whole scenario to its end, wait once for the slowest signal the mission
reads (60 s when it reads traces), then run every query against the
window recorded in step 4. Never interleave requests, waits, and
queries outside the query points the record declares: a wait after
every request batch turns a 3-minute scenario into 4 minutes of sleep.
The wait — a fixed sleep or a bounded poll — is a `sleep` inside a
helper script run in the foreground (`references/long-scenarios.md`),
inside the turn — never a background job whose completion notification
the turn waits for, never a turn ended to wait. A Monitor-style
background notifier is a wait only in a main conversation, which is
re-invoked when it fires; a subagent's turn ends first, so there the
helper is the only wait.

Every file this skill writes — that helper, a poller and its state, a
captured output — goes in one scratchpad subdirectory this run alone
owns: the directory the caller named, else `<scratchpad>/<run slug>/`,
created before the first file. Parallel missions share the scratchpad
root, and a sibling's file overwriting yours, or a previous run's left
where yours goes, is silent.

A mission that must read the store at several points — each reset
wipes it, so a lifecycle test whose subject is the reset has one store
per reset — declares them on the record's `Query points:` line with the
reason each one exists, and pays each point one wait sized to the
slowest signal **that point** reads (10 s when it reads metrics only).
A remote backend's wait is not this skill's to size — `observe-run`
owns it (the backend's documented ingest latency, or a bounded proof
query); this skill stays scoped to locally running services.

## Output

The scenario block from step 4 (or `references/benchmark-replay.md`'s
record for a stored benchmark), ready
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
- A driven request that calls a paid model spends money — every warmup
  and every iteration of it. Like a drive at a remote target, it is
  confirmed by the caller before the first such request goes out: the
  operation, the model when known, and the request count with the
  warmup included; the mission block saying the spend is accepted is
  that confirmation, a stored benchmark's manifest never is — it
  authorizes the load's shape, not the bill. No confirmation, no
  drive: leave the model-calling operations out, or stop, and say
  which in the record. An operation calls a paid model when the
  mission says so, when the stack's traces already show `gen_ai.*`
  spans under it, or when the service's own contract names a model;
  an operation you cannot rule either way is left out too, named in
  the record as unruled — a stop-and-report, never a question the
  drive waits on.
