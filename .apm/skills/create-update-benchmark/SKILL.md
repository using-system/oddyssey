---
name: create-update-benchmark
description: Persist a k6-benchmark-expert-authored benchmark (script + manifest) into .odd/benchmarks/<name>/ - naming, versioning, the commit, recalling the benchmarks already stored for a service. A benchmark is not a report - it is living source, updated in place via reviewed diffs, not append-only. Use when a benchmark's authored content needs to land in the repo, or when an update to an existing benchmark needs to be recalled before authoring a new one.
---

# Create / Update a Benchmark

`.odd/benchmarks/<name>/` is the memory contract's one exception
(`odd-memory`): a benchmark is living source, not a run record -
updated in place through reviewed diffs, git history rather than file
accumulation being its memory. Writing and updating is this skill's
whole point; the rest of the contract (where the memory lives, no
secrets, the work branch and the lone commit, the reply) applies as
written there.

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
- **Commit discipline** (the memory contract): the work branch is
  `docs/odd-benchmark-<name>`; the commit carries the benchmark's files
  alone, subject `docs(odd): benchmark <name>` for a new benchmark,
  `docs(odd): update benchmark <name>` for a diff-reviewed update; the
  reply states the stored path, so `show-benchmark` can point at it.
- **Refusing a literal credential.** Before persisting, scan the script
  for anything that looks like an inlined secret (the memory contract's
  no-secrets rule, applied to source) - refuse and say why rather than
  committing it. `k6-guides`' `scripting.md` documents the correct
  alternative (`k6/secrets`, named environment variables) for the agent
  to use instead. On a host that runs the package's lifecycle hooks, a
  hook flags what slipped through, after the write.

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

- **Not inventoried by `/odd-status`.** `get-status` inventories the
  two report directories and the decisions ledger; benchmarks are not
  loop state and never appear in its inventory (its commit test is a
  different matter - next bullet).
- **Visible to the verify-vs-re-measure boundary** (the memory
  contract): a commit that updates a benchmark counts as changed code,
  so a replay after it is a verification, never a re-measure. Which of
  the baseline's findings that verification can
  rule depends on what moved (the benchmark's own defects always; the
  service's before/after only when the load did not change) - the
  `/odd-verify` prompt owns that rule.
