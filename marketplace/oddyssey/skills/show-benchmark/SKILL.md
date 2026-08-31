---
name: show-benchmark
description: Render a short synthesis of a persisted k6 benchmark for the human closing an /odd-instrument-bench mission - the stored path, what the benchmark exercises, the next recommended action - never a replacement for the script/manifest itself. Use when an /odd-instrument-bench mission ends and the final answer must synthesize what create-update-benchmark just stored instead of dumping it raw.
---

# Show a Benchmark

Every authoring mission in this repo closes with a `show-*` synthesis
instead of dumping its stored deliverable into the conversation
(`show-otel-instrumentation-report`, `show-observe-run-report`) -
authoring a k6 benchmark is no exception.

## What to render

- **Stored path** - where `create-update-benchmark` wrote the script and
  manifest (`.odd/benchmarks/<name>/`).
- **What it exercises** - target service, the endpoints/operations in
  scope, the test type (smoke/load/stress/soak/spike/breakpoint).
- **Next recommended action** - how to actually run it, e.g.
  `/odd-observe check checkout under benchmark checkout-read-heavy` (the
  exact composition with `/odd-observe`'s `benchmark:` field is out of
  scope for this authoring implementation - phrase the next action
  generically until execution is built, never invent a syntax that
  doesn't exist yet).
- **For an update**: a short headline of what changed against the
  previous version - the full diff already lives in the commit, this is
  the human-readable one-liner, not a diff dump.

## What never to render

- The script or manifest's full content - the stored files are the
  deliverable, this skill is a pointer to them, never a replacement.
  Same separation `show-otel-instrumentation-report` keeps from the
  report it summarizes.

## What this skill reads

Only what `create-update-benchmark` just wrote and returned - no k6
knowledge, no independent investigation of the service. If the stored
path or benchmark name is missing from what it's handed, that is an
upstream contract failure to surface, not something to guess at.
