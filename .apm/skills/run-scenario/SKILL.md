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
ad-hoc drive is this skill's `scripts/drive_scenario.py` (step 2); a
stored benchmark's replay is `k6-guides`' `scripts/replay_benchmark.py`
(`references/benchmark-replay.md`). A curl loop, a helper with a `sleep`
in it, a poller written for either yields a different command each time —
two runs then measure two things.

## Read by situation

Steps 1 to 5 and the rules are the method; a reference is read by the
block that applies, never whole:

| Situation | Reference |
| --- | --- |
| Every drive: the clean-base order and the reset decisions, the identity the queries are qualified by and the instance read from the rows, the run's t0 after the warmup — a port already served, a remote target the run cannot launch, a restart that is not possible, a reset that is forbidden | [references/run-identity.md](references/run-identity.md), the block that applies |
| An iteration that is expensive or non-deterministic; the watch of a run someone else drives, on a backend that ships no watch script | [references/long-scenarios.md](references/long-scenarios.md) |
| A stored k6 benchmark under `.odd/benchmarks/<name>/` — driven here, or driven elsewhere and only watched | [references/benchmark-replay.md](references/benchmark-replay.md), in place of step 2; its watching section for a run someone else drives |

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

## 2. Drive it

What you decide: the operations (step 1), the count per operation (step
3), concurrency or not, the signal the flush wait is sized by (step 5),
the run slug and the prompt's name. Everything else is the script's:

```bash
python3 <skills>/run-scenario/scripts/drive_scenario.py http://127.0.0.1:<port> --run-slug <slug> --prompt <observe|verify> --op 'GET /api/users' --op 'POST /api/orders {"sku": "A1"}' --count 30 --wait-for traces --out <scratch>/<slug>
```

The whole surface: the base URL (positional; `127.0.0.1`, never
`localhost` — refused; the mission's or the `Machine:` line's when it
carries one), `--run-slug`, `--prompt`, `--op 'METHOD PATH [COUNT]
[BODY]'` (repeatable; the count overrides `--count` for that operation,
the body goes out as `application/json`), `--ops <file>` (one per line),
`--count` (default 30), `--warmup` (default 5, discarded),
`--concurrency` (default 1), `--prefix` (default `0ddc0ffe`), `-H 'Name:
value'` (repeatable; a credential-named header's value is never
recorded), `--timeout` (per request, default 60 s), `--wait-for
traces|metrics|none` (default `traces`), `--scenario <name>` (default the
slug), `--out <dir>`, `--detach`, `--status <dir> [--wait <duration>]`,
`--dry-run` (the plan and the command, nothing sent), `--json` (the
record as one object) — nothing else, so `--help` has nothing to add and
the file nothing to read. It prints step 4's record, three lines of
which are `<yours: ...>` placeholders to fill, and writes
`drive-record.json` and `requests.jsonl` under `--out` — the directory
this run alone owns, `<scratch>/<slug>/` unless the caller named one: a
sibling's file overwriting yours is silent.

A scenario longer than a tool call is the same invocation with
`--detach` (returns at once), then `--status <dir> --wait <the length
plus a margin>` — exit 3 when the bound passes with the drive still
going, run it again. Never a poller or a helper around it, never a turn
ended to wait: as a subagent, ending the turn ends the mission.

## 3. Iterate enough to quote a number

- **>= 30 requests per operation** before quoting a p95 — an operation
  being the unit the service serves distinctly: on an HTTP server the
  method and the route together, so two verbs sharing a route need the
  count each. Below that, report observations, not quantiles.
- **~100** before quoting a p99.
- Sequential by default. If concurrency is part of the question, state
  the level explicitly — it changes every latency number.
- Keep inputs deterministic: fixed IDs, fixed payloads, a fixed seed. A
  random payload is not replayable; if randomness is unavoidable, record
  the seed.
- An iteration that is expensive or non-deterministic:
  `references/long-scenarios.md`.

## 4. Record verbatim

The record is what the script printed — the deliverable, quoted in the
report and re-run from its `Commands:` line after a fix:

```text
Scenario: <name>
Base URL: http://127.0.0.1:<port>
Listeners: none   # or: :8000 served by 41234 uvicorn (127.0.0.1) and 51022 com.docker (*)
Backend:  <yours: odd_stack_reset, env: {...} - or "no reset - separated by the slug and the window">
Instance: <yours: read from the run's own rows after the wait>
Identity: User-Agent "odd-<prompt>/<slug>" (+ "-warmup" on the warmup); traceparent "00-<prefix><run8><seq:016x>-<seq:016x>-01", run8 = sha256(<slug>)[:8] = <hex>, trace ids start <prefix><run8>; one sequence run-wide from 1
Warmup:   5 requests per operation (discarded; seq 1-10)
Load:     30 requests per operation, sequential (seq 11-70)
Started (UTC): 2026-08-17T10:04:12Z
Ended   (UTC): 2026-08-17T10:05:03Z
Query points: 1 (after Ended; after the 60 s flush wait for traces)
Commands:
  python3 <skills>/run-scenario/scripts/drive_scenario.py http://127.0.0.1:<port> --run-slug <slug> ...   # as printed
Requests:
  GET http://127.0.0.1:<port>/api/users x30 (seq 11-40) -> 200:30
  POST http://127.0.0.1:<port>/api/orders {"sku": "A1"} x30 (seq 41-70) -> 201:28, error:2
Not reproducible: <yours: auth token / seeded data / time-dependent input, or "none">
```

- `Started`/`Ended` are the observation window of every query.
- `Backend:` carries how the stack was (re)started **including any
  `env`**: a bare `odd_stack_reset` reapplies the env persisted in
  `stack_config.local`; only the credential-named variables the reset
  result lists under `env_not_persisted` must be passed again. A reset
  the mission requires (`references/run-identity.md`) is a `Commands:`
  line of its own, with its env and its reason.
- `Query points:` is the one point the script pays for; a mission that
  must read the store at several points (one store per reset in a
  lifecycle test) runs the script once per point and lists them here,
  each with its reason.
- A stored benchmark's record is `references/benchmark-replay.md`'s.

## 5. Wait for the flush — once per query point

- `--wait-for` is sized by the slowest signal the point reads: **~60 s**
  for traces to become searchable on the local stack (a trace fetch by
  id may work before search does — cross-check a suspicious search
  result against a fetch), **~10 s** for metrics.
- Paid **once per query point, after the last request that point reads**
  — never per query, never per request batch: a wait after every batch
  turns a 3-minute scenario into 4 minutes of sleep.
- Inside the turn: the script blocks through it, foreground or `--status
  --wait`; a background notifier fires after a subagent's turn has ended.
- A remote backend's wait is `observe-run`'s to size (its documented
  ingest latency, or a bounded proof query): `--wait-for none`, then that.

## Output

The record above (or `references/benchmark-replay.md`'s for a stored
benchmark), ready to paste into an observation report — the run record,
and the replay instruction in the measurement protocol — and ready to
re-run unchanged after a fix.

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
