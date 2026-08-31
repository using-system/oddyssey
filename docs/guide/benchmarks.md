# Benchmark authoring, running, and verifying

A k6 load-test benchmark, authored once as reviewed code and replayed
identically for as long as it stays useful. This guide walks the full
lifecycle in order: author, run, verify.

**Status: authoring only, for now.** Running a stored benchmark through
`/odd-observe` and verifying one through `/odd-verify` are specified
(see the design spec linked below) but not yet implemented — this page
covers what exists today and will grow the Run/Verify sections once
that lands.

## Author

`/odd-instrument-bench` investigates a service and writes a k6 benchmark
— a script plus a manifest — into `.odd/benchmarks/<name>/`, through the
`k6-benchmark-expert` agent. It never runs what it writes.

```text
/odd-instrument-bench author a load benchmark for checkout, stress test, p95 under 300ms
```

Before dispatching the agent, the prompt asks back whatever only a
human can decide — test type, thresholds, new benchmark or an update to
an existing one, the target environment — and proposes a load
shape/duration for you to confirm. Everything else (which endpoints,
what the service already looks like from past `.odd/` reports) the
agent discovers on its own. The full breakdown of what's asked versus
discovered is in the `k6-guides` skill's `authoring-inputs.md`
reference.

The mission closes with a short synthesis of the stored benchmark (the
`show-benchmark` skill) — the stored path, what it exercises, and the
next step. The script and manifest themselves are never dumped into the
conversation; the stored files under `.odd/benchmarks/<name>/` are the
deliverable.

Updating an existing benchmark, when a service's endpoints have
drifted, follows the same prompt — the agent proposes the change as a
reviewed diff against the stored version, never a silent replacement.

Unlike this project's committed reports, a benchmark is **not**
append-only: it's living source, updated in place and reviewed like any
other code change (see `create-update-benchmark`). See
[reports.md](reports.md) for how that differs from the report stores'
own immutability rule.

## Run

*Not yet implemented.* The design (see the spec below) is a `benchmark:
<name>` field on `/odd-observe`'s existing `drive`/`observe` modes —
`drive` runs the stored plan itself, `observe` watches someone else run
it while still citing the plan by name and revision.

## Verify

*Not yet implemented.* The design replays the benchmark at the git
revision an observation recorded it at, ruling on the manifest's
declared thresholds against telemetry (metrics, traces, logs) — never
k6's own pass/fail summary.

## Full design

The complete design, including what's deferred and why, is in
[the design spec](../superpowers/specs/2026-08-31-k6-benchmark-authoring-design.md)
and its tracking issue,
[#75](https://github.com/using-system/oddyssey/issues/75).
