---
name: create-update-benchmark
description: Persist a k6-benchmark-expert-authored benchmark (script + manifest) into .odd/benchmarks/<name>/ - naming, versioning, the commit, recalling the benchmarks already stored for a service. A benchmark is not a report - it is living source, updated in place via reviewed diffs, not append-only. Use when a benchmark's authored content needs to land in the repo, or when an update to an existing benchmark needs to be recalled before authoring a new one.
---

# Create / Update a Benchmark

`.odd/benchmarks/<name>/` is a **third kind** of `.odd/` content, and it
does **not** inherit the report stores' immutability rule
(`create-observe-run-report`, `create-otel-instrumentation-report`):
`AGENTS.md`'s "the `.odd/` memory is append-only" and
`docs/guide/reports.md`'s "a report is never edited after the fact"
govern the **committed reports** specifically - `observe-run-reports/`,
`otel-instrumentation-reports/`, and `decisions.md`. A benchmark is
living source, not a run record: git history, not file accumulation, is
its memory. Writing and updating is this skill's whole point, not an
exception to some other rule.

## What this skill owns

- **Persisting** the k6 script and manifest `k6-benchmark-expert` hands
  it, into `.odd/benchmarks/<name>/` - the directory name is the
  benchmark's identity.
- **Recall, two-step**: the target **service** returns the set of
  benchmarks that already exist for it (so the agent cannot duplicate
  one it never saw); the benchmark **name** identifies the single
  artifact an update rewrites. List every benchmark under
  `.odd/benchmarks/` and check each manifest's declared target service
  before the agent authors anything new.
- **Reviewed diffs, never silent overwrites.** When the agent proposes
  updating an existing benchmark, the change is presented as a diff
  against the stored version - the maintainer reviews it exactly like
  any other committed change, through the normal PR flow. This skill
  never overwrites a stored benchmark without that diff being visible.
- **Commit discipline**, inherited from the report-writing skills:
  - never commit on the default branch - create or switch to a work
    branch first;
  - stage and commit the benchmark's files **alone** (never bundled with
    unrelated changes);
  - commit subject: `docs(odd): benchmark <name>` for a new benchmark,
    `docs(odd): update benchmark <name>` for a diff-reviewed update;
  - state the stored path in the reply, so `show-benchmark` (a
    different skill) can point at it.
- **Refusing a literal credential.** Before persisting, scan the script
  for anything that looks like an inlined secret (the same discipline
  the report skills already apply to report bodies) - refuse and say why
  rather than committing it. `k6-guides`' `scripting.md` documents the
  correct alternative (`k6/secrets`, named environment variables) for
  the agent to use instead.

## What this skill does not own

- Any k6 knowledge - it persists whatever content the agent decided,
  unopinionated about whether the script or manifest is any good. That
  judgment belongs to `k6-benchmark-expert`, informed by `k6-guides`.
- The manifest's schema - this skill stores whatever shape the manifest
  has; it does not define that shape.
- Deleting a benchmark. A benchmark whose target service is gone is
  stale source, not something this skill garbage-collects - removing one
  is a human's PR, like removing any other dead source file.

## Lifecycle notes

- **Invisible to `/odd-status`.** `get-status` inventories the two
  report directories and the decisions ledger; benchmarks are not loop
  state and never appear there.
- **Visible to the verify-vs-re-measure boundary.** `/odd-verify` and
  `/odd-status` ignore commits that touch only the loop's memory - the
  two report stores and the decisions ledger - but `.odd/benchmarks/`
  is living source, not memory: a commit that updates a benchmark
  counts as changed code, so a replay after it is a verification, never
  a re-measure. Which of the baseline's findings that verification can
  rule depends on what moved (the benchmark's own defects always; the
  service's before/after only when the load did not change) - the
  `/odd-verify` prompt owns that rule.
