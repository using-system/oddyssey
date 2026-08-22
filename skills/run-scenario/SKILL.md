---
name: run-scenario
description: Drive a reproducible request scenario against a locally running service and record it verbatim, so the telemetry it produces can be compared with a later run. Use when traffic must be generated before observing a service, when an observation report needs a replayable scenario, or when verifying after a fix that the same scenario now measures better.
---

# Run a Scenario

One protocol on both ends of the ODD loop: the same commands that produced
the numbers in an observation report produce the numbers that verify the
fix. A scenario that cannot be replayed verbatim makes before/after
comparison an impression, not a measurement.

## 1. Decide what to exercise

In order of preference:

1. **The caller's list** — endpoints, payloads, and counts given in the
   mission. Use them as-is; do not "improve" them.
2. **Traces already in the stack** — the operations Tempo has seen for this
   service (`gcx traces query` on `{resource.service.name="<svc>"}`, group by
   span name) are what the service actually serves. Configure gcx against
   the local stack with the `gcx-local-stack` skill first.
3. **The service's own contract** — an OpenAPI/Swagger document, a route
   table, a CLI entry point in the repository (read-only).

Prefer a handful of representative operations covered properly over every
endpoint covered once. Note anything you deliberately left out.

## 2. Warm up

Send a few requests per endpoint (typically 5) before measuring: JIT
compilation, connection pools, lazy caches, and first-hit schema loads all
land in the first requests and distort a small sample. Discard the warmup
from the quoted numbers, and say in the record that it was discarded.

## 3. Iterate enough to quote a number

- **>= 30 requests per endpoint** before quoting a p95. Below that, report
  observations, not quantiles.
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
Base URL: http://localhost:<port>
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
