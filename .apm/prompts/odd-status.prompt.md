---
description: Where is the ODD loop? Read the repository's .odd/ history and render per-service loop state, the findings ledger, trends, open telemetry gaps, and the next recommended action - read-only, no backend queries, no report written
---

Answer "where is the loop?" for this repository, from its committed
memory alone.

Sources - and nothing else:

- `.odd/observe-run-reports/` and `.odd/otel-instrumentation-reports/`:
  frontmatters first, bodies only where a section below needs their
  structured tables or a verification's rulings;
- git metadata about the repository and those files: report commit
  dates, and each report's `revision` field against the commits that
  came after it.

Never query a backend, never start the stack, never write or edit a
report - this prompt reads the loop, it does not advance it. The
status renders in the conversation, as tables - never a committed
artifact.

- Arguments: $ARGUMENTS
- Expected fields (optional, free-form): service name(s), a stack
  (`local`, `grafana`, ...) and/or a deployment environment (`prod`,
  `uat`, ...) to restrict the status to. No arguments = the whole
  picture.

Build the status in this order:

1. **Inventory - frontmatters only.** List both directories and read
   every frontmatter, no bodies yet. No `.odd/` directory or no
   reports at all: say the loop has not started here, point at
   `/odd-instrument` or `/odd-observe`, and stop - that IS the status,
   not a failure.
2. **Per-service loop state.** One row per service (`services` for
   observation reports; an instrumentation report contributes to the
   services its plan covers, `project` names its scope): last
   observation (date, `stack`, `environment`, mode, `workload` when
   present), last verification (`mode: verify` reports - their
   `verifies` value names what they replayed) with its verdict from the
   report body, and the chain as the files tell it:
   observed -> fixed -> verified.
   "Fixed" means commits landed after the report's `revision`,
   **excluding commits that only touch `.odd/` or documentation** -
   the loop's own memory is not a fix. Scope the commit test to the
   service's path when a report names one (an instrumentation
   report's `project`); otherwise say the count is repo-wide, not
   service-scoped. A verification covers the commits its own
   `revision` has as ancestors - but in a squash-merge workflow that
   `revision` never becomes an ancestor of the merged history, so
   ancestry alone cannot prove coverage: a commit whose squash
   introduced the verification report itself is covered by that
   verification, and when ancestry is otherwise inconclusive, say
   coverage is uncertain rather than ruling a verification due. When
   a report carries no `revision`, its commit date - already a
   source - is the substitute boundary.
   Pre-convention reports (no `verifies` field) leave the chain
   "unknown (pre-convention)" - state it, never reconstruct it from
   prose.
3. **Findings ledger.** From each report's ranked findings table and
   each verification's rulings: open, fixed-and-verified, or
   regressed, with severity - the burn-down of the loop's backlog. A
   finding no verification ever ruled on stays open, whatever a commit
   message claims.
4. **Trends.** For operations appearing in the per-operation summary
   table of two or more reports of the same service, stack, environment
   and `workload`: p50/p95/p99 and error rate across runs - improved /
   regressed / stable, with the stored numbers. Comparability is
   stricter than the frontmatter: reports whose `workload` differs
   are incomparable, and for drive-mode reports (and verifications
   replaying one) so are runs whose
   recorded scenario or process identity (`instance`,
   `process_restarted`) differ - a driven session and a
   process-per-call run measure different things whatever the
   frontmatter says. A verification and its baseline replay the same
   scenario by construction and always compare. List incomparable
   runs apart, never diff them. Stored numbers only - no live
   queries.
5. **Open telemetry gaps.** Gaps recorded in report bodies and not
   closed by a later verification ruling or instrumentation report.
   When gaps dominate a service's picture, the recommendation below
   should say instrument, not observe.
6. **Next recommended action** - the maturity principle
   operationalized, per service: a **verification is due**
   (service-relevant commits - step 2's rule - landed after the last
   report's `revision` and no verification covers them), a **new
   observation is due or overdue** (the cadence
   of past observation dates has lapsed, or recent verdicts keep
   churning), or the **loop can rest** (recent verification, stable
   verdicts, no unverified change). Every recommendation cites its
   inputs - dates, verdicts, revisions - evidence over impressions
   applies to the meta-loop too.

Degrade gracefully everywhere: a single report, reports predating
newer frontmatter fields, a body missing a structured section - render
what exists, mark what cannot be known ("no verification yet", "chain
unknown"), and never fail the whole status over one unreadable report.
