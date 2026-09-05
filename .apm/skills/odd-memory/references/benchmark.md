# Benchmarks

`.odd/benchmarks/<name>/` is the contract's one exception
(`SKILL.md`): a benchmark is living source, not a run record -
updated in place through reviewed diffs, git history rather than file
accumulation being its memory. Writing and updating is this reference's
whole point; the rest of the contract (where the memory lives, no
secrets, the work branch and the lone commit, the reply) applies as
written there.

## Where benchmarks live

The persistence stores the k6 script and manifest `k6-benchmark-expert`
hands it, into `.odd/benchmarks/<name>/` - the directory name is the
benchmark's identity.

## Recall

Two-step: the target **service** returns the set of benchmarks that
already exist for it (so the agent cannot duplicate one it never saw);
the benchmark **name** identifies the single artifact an update
rewrites. List every benchmark under `.odd/benchmarks/` and check each
manifest's declared target service before the agent authors anything
new.

## Rules

- **Reviewed diffs, never silent overwrites.** When the agent proposes
  updating an existing benchmark, the change is presented as a diff
  against the stored version - the maintainer reviews it exactly like
  any other committed change, through the normal PR flow. The persistence
  never overwrites a stored benchmark without that diff being visible.
- **Commit discipline** (the memory contract): the work branch is
  `docs/odd-benchmark-<name>`; the commit carries the benchmark's files
  alone, subject `docs(odd): benchmark <name>` for a new benchmark,
  `docs(odd): update benchmark <name>` for a diff-reviewed update; the
  reply states the stored path, so `## Show` below can point at it.
- **Refusing a literal credential.** Before persisting, scan the script
  for anything that looks like an inlined secret (the memory contract's
  no-secrets rule, applied to source) - refuse and say why rather than
  committing it. `k6-guides`' `scripting.md` documents the correct
  alternative (`k6/secrets`, named environment variables) for the agent
  to use instead. On a host that runs the package's lifecycle hooks, a
  hook flags what slipped through, after the write.

## What the persistence does not own

- Any k6 knowledge - it persists whatever content the agent decided,
  unopinionated about whether the script or manifest is any good. That
  judgment belongs to `k6-benchmark-expert`, informed by `k6-guides`.
- The manifest's schema - the persistence stores whatever shape the manifest
  has; it does not define that shape.
- Deleting a benchmark. A benchmark whose target service is gone is
  stale source, not something the persistence garbage-collects - removing one
  is a human's PR, like removing any other dead source file.

## Lifecycle notes

- **Not inventoried by `/odd-status`.** `get-status` inventories the
  two report directories and the ruling ledgers; benchmarks are not
  loop state and never appear in its inventory (its commit test is a
  different matter - next bullet).
- **Visible to the verify-vs-re-measure boundary** (the memory
  contract): a commit that updates a benchmark counts as changed code,
  so a replay after it is a verification, never a re-measure. Which of
  the baseline's findings that verification can
  rule depends on what moved (the benchmark's own defects always; the
  service's before/after only when the load did not change) - the
  `/odd-verify` prompt owns that rule.

## Show

Every authoring mission closes with a synthesis instead of dumping its
stored deliverable into the conversation - authoring a k6 benchmark is
no exception.

### What to render

- **Stored path** - where the persistence step above wrote the script and
  manifest (`.odd/benchmarks/<name>/`).
- **What it exercises** - target service, the endpoints/operations in
  scope, the test type (smoke/load/stress/soak/spike/breakpoint).
- **Validation** - what the manifest records: `k6 inspect` passed (k6
  version, date) and the smoke's result - passed (local or remote
  target, the URL only when the manifest stores it), declined, not
  applicable (with the scenarios it could not reach), or the functions
  it did not cover - and the threshold cross-check: each threshold,
  the service-side floor it was checked against or none found, and the
  outcome (reachable, kept with the floor acknowledged, or the value
  the caller changed it to). One or two lines; a benchmark whose
  manifest records no validation is an upstream contract failure to
  surface, not a line to invent.
- **Next recommended action** - how to actually run it:
  `/odd-observe run .odd/benchmarks/<name>/` (drive mode with that
  benchmark, see `docs/guide/benchmarks.md`).
- **For an update**: a short headline of what changed against the
  previous version - the full diff already lives in the commit, this is
  the human-readable one-liner, not a diff dump.

### What the synthesis reads

Only what the persistence step above just wrote and returned, per
the contract's synthesis rules (`SKILL.md`) - never the script or
manifest's full content, no k6 knowledge, no independent investigation
of the service. If the stored path or benchmark name is missing from
what it's handed, that is an upstream contract failure to surface, not
something to guess at.
