---
name: get-status
description: Render the state of the ODD loop from the repository's committed .odd/ history and git alone - per-service loop state, findings ledger, trends, open telemetry gaps, next recommended action - read-only, no backend queries, no report written. Use when answering where the loop is, when /odd-status runs, or when a status must be computed offline from the clone.
---

# Get the ODD Loop Status

Answer "where is the loop?" for this repository, from its committed
memory alone. Every input is already in the clone — the stored reports,
the decisions ledger, and git — so the status costs no backend query, no
running stack, and no network: it is what the loop wrote down about
itself.

## Sources — and nothing else

- `.odd/observe-run-reports/` and `.odd/otel-instrumentation-reports/`:
  frontmatters first, bodies only where a step below needs their
  structured tables or a verification's rulings;
- git metadata about the repository and those files: report commit
  dates, and each report's `revision` and `tree_anchor` fields against
  the commits that came after it;
- `.odd/decisions.md`, the findings decision ledger — read through the
  ledger contract the `record-finding-decision` skill owns: that skill
  is the format's authority, this one only reads what it wrote. A
  missing file means no decision has been recorded yet, which is a
  fact, not an error.

The caller may restrict the status to service name(s), a stack (`local`,
`grafana`, ...) and/or a deployment environment (`prod`, `uat`, ...).
When no filter is named, every stored report qualifies — no arguments is
the whole picture, not an empty scope.

Never query a backend, never start the stack, never write or edit a
report, a ledger, or any other file — this skill reads the loop, it does
not advance it. The one write in the status surface belongs to the
`record-finding-decision` skill. The status renders in the conversation,
as tables — never a committed artifact.

## Compute the facts first, then reason

Every deterministic input of the build order below — the frontmatters,
each report's commit boundary, the tree-anchor comparison, the commits
that landed since, the lifted tables, the ledger cross-reference — is
computed by the script bundled with this skill, in **one shell call**,
before any reasoning starts:

```bash
python3 <this skill's directory>/scripts/odd_status.py \
  [--service <name>]... [--stack <stack>] [--env <environment>]
```

Pass the caller's scope as flags — the service name(s) exactly as
named, the stack, the environment; nothing when the caller named
nothing. The script prints one JSON fact sheet on stdout:

- `loop_started`, `inventory` (the distinct services, stacks, and
  environments across every stored report) and `matched` — enough to
  answer with step 1's stop, or with the filter-matches-nothing
  statement, without opening a file;
- one entry per matched report: its frontmatter and
  `frontmatter_errors`; its `commit` (the commit that added the file)
  and whether its `revision` resolves in this clone; its
  `tree_anchor_diff` against HEAD — `unchanged` (a count),
  `non_runtime` (documentation files and editor/CI configuration only,
  plus what `--non-runtime` names; `--runtime` keeps an entry out of
  it whatever its name), `unclassified`, `only_in_anchor`,
  `only_at_candidate`, `.odd` ignored, and `changed_paths`, the files
  behind each differing entry when the revision resolves (a complete
  `count`, a capped list of `paths`); its
  `commits_since` — `boundary` is `revision` when it resolves,
  `commit-date` otherwise (the report's own commit then left out), or
  `none` for an uncommitted report (then `count` is null and means
  nothing) — with memory-only commits excluded, the scope narrowed to
  an instrumentation report's
  `project` path when that path exists, a complete `count`, and a
  capped list where each commit names the top-level `entries` it
  touched, so a documentation-only commit is told from a fix without
  another git call; the `benchmarks` its body names, each with the
  section naming it and the commits that touched it (the one the
  scenario record names is the run's; a mention elsewhere is not);
  its opening paragraph as `headline`, its `**Verdict` paragraphs, the
  `scenario_record` lifted from section 1 (its own, shorter cap), its
  `finding_ids` (section 3's first column — on a verification that
  column names checks, so read it as what the table lists, not as the
  report's findings), and its numbered sections with their tables
  (sections 2, 3, and 5 by default, plus 7 on a `verify` or
  `re-measure` report, whose rulings may sit in its protocol table)
  and prose (3 and 5 by default);
- a `detail` level per report. The newest three reports of each
  lineage — one service set on one stack and environment, or one
  instrumentation `project` on one stack — are `full`; the older ones
  are `compact`: no sections, no scenario record, `commits` null (the
  `count` stays), headline and verdict paragraphs cut at 300
  characters. Every report, whatever its detail, keeps its
  `findings` — id, title, severity, ruling, and the `section` the row
  came from: section 3's rows always, and on a `verify` or
  `re-measure` report every row of a table carrying a ruling column,
  wherever it sits — so the ledger and the burn-down read from the
  compact entries too. `--recent <n>` widens the window, `--recent
  all` lifts everything, and a scope (`--service`, `--stack`, `--env`)
  shrinks the set the window applies to;
- the `ledger`: every row with its `status` (`ok`, or `skipped` with
  the reason — wrong column count, malformed reference, unknown report,
  unknown finding, the finding checked against the report's uncapped
  section 3), and `effective`, the latest `ok` row per finding key.

The script computes facts and rules on nothing: the chain, the
comparability of runs, what an `unclassified` tree entry means, and
the recommendation stay with the steps below. Read the sheet as the
inventory and as the material of every step; open a report body only
when the sheet flags a truncation (`text_truncated`, `truncated_cells`,
`scenario_record_truncated`, `truncated` commits, a `…` ending a
compact paragraph) on something a step needs, or when a step needs a
section the sheet did not lift — for a `compact` report, re-run the
script scoped to its lineage with a wider `--recent` before opening
its body — and run a git command of your own only when the sheet
leaves a boundary uncertain. `--help` lists the caps and the lift
options and how to
change them.

When `python3` is missing, the script is not next to this file (an
install that dropped `scripts/`), or it exits non-zero, say so in one
line and build the status by hand, exactly as the steps below describe
— the script is a shortcut to the same facts, never a different status.

## Build the status in this order

1. **Inventory — frontmatters only.** List both directories and read
   every frontmatter, no bodies yet. No `.odd/` directory or no reports
   at all: say the loop has not started here, point at
   `/odd-instrument-otel` or `/odd-observe`, and stop — that IS the
   status, not a failure.
2. **Per-service loop state.** One row per service (`services` for
   observation reports; an instrumentation report contributes to the
   services its plan covers, `project` names its scope): last
   observation (date, `stack`, `environment`, mode, `depth` — `full`
   when the frontmatter has none — `workload` when present), last
   verification (`mode: verify` reports — their `verifies` value names
   what they replayed) with its verdict from the report body — a
   `depth: quick` verification renders its coverage
   (`PASS (quick, 3 of 5 ruled)`) and satisfies "verified" only for
   the items it ruled, never for the service as a whole; a
   verification's presence rulings satisfy "verified" only for the
   items ruled `closed`, `present, unattributed` closes nothing — and
   the chain as the files tell it:
   observed -> fixed -> verified. A `mode: re-measure` report is an
   observation event, never a verification: it replayed the protocol of
   the report its `verifies` names without ruling on a fix — count it as
   the last observation when newest, and never let it satisfy "verified"
   in the chain.
   "Fixed" means commits landed after the report's `revision`,
   **excluding commits that only touch the loop's own memory or
   documentation** — the memory being the append-only report stores
   and the ledger (`.odd/observe-run-reports/`,
   `.odd/otel-instrumentation-reports/`, `.odd/decisions.md`), never
   `.odd/benchmarks/`: a benchmark is living source, and a commit
   changing one is a fix like any other. Scope the commit test to the
   service's path when a report names one (an instrumentation report's
   `project`); otherwise say the count is repo-wide, not service-scoped.
   A verification covers the commits its own `revision` has as ancestors
   — but in a squash-merge workflow that `revision` never becomes an
   ancestor of the merged history, so ancestry alone cannot prove
   coverage: a commit whose squash introduced the verification report
   itself is covered by that verification, and when ancestry is
   otherwise inconclusive, say coverage is uncertain rather than ruling
   a verification due. When a report carries a `tree_anchor`, that is
   the **preferred boundary**: compare its entry hashes against
   `git ls-tree` of the candidate commit, ignoring `.odd` (its
   top-level hash moves with every report written) and every entry
   that cannot change the observed service's runtime behavior —
   documentation is the canonical case, but so are CI configuration,
   generated/packaging artifacts, and release-metadata files — then
   test the benchmark by path: the one the report's scenario record
   names (`.odd/benchmarks/<name>/`) — nothing when it names none, a
   benchmark the run did not use cannot be its fix; commits touching
   that path since the report (`git log <revision>..HEAD -- <path>`
   when `git rev-parse --verify <revision>^{commit}` succeeds,
   otherwise `git log --since=<the report file's own commit date> --
   <path>`, the report's own commit ignored). Equal hashes and no
   benchmark
   commit mean no code change, and the comparison resolves in any
   clone whatever the merge strategy; when the only differing entries
   are ones you cannot classify, the boundary is uncertain — say so,
   never rule "code changed". When a report carries neither an anchor
   nor a `revision`, its commit date — already a source — is the
   substitute boundary.
   Pre-convention reports (no `verifies` field) leave the chain
   "unknown (pre-convention)" — state it, never reconstruct it from
   prose.
3. **Findings ledger.** From each report's ranked findings table, each
   verification's rulings, and the decisions ledger: open,
   fixed-and-verified, regressed, or declined, with severity — the
   burn-down of the loop's backlog. A finding no verification ever ruled
   on stays open, whatever a commit message claims — `not ruled (quick)`
   in a quick verification is not a ruling — unless the
   decisions ledger declines it.
   Cross-reference every finding against `.odd/decisions.md` on the key
   that ledger uses: `<exact report filename> / <finding ID as the
   report's ranked-findings table names it>` — the exact filename is
   what disambiguates finding IDs, which are report-local (two reports
   can both have an "F4"). Rows are appended, never rewritten, so **the
   latest row for a finding wins**: when it carries a declining verdict
   (`wontfix`, or any verdict other than `open`) the finding renders
   **declined** — its verdict, decision date, and rationale in place of
   the open state — and when it carries `open` the finding is reopened,
   back to whatever the reports rule. A finding with no ledger row
   renders exactly as it would without the ledger.
   Count open, fixed-and-verified, regressed, and declined **separately**
   in the burn-down: a declined finding was decided, not fixed, and
   merging the two would hide the backlog's real shape.
4. **Trends.** For operations appearing in the per-operation summary
   table of two or more reports of the same service, stack, environment
   and `workload`: p50/p95/p99 and error rate across runs — improved /
   regressed / stable, with the stored numbers. Depth does not break
   comparability: section 2's numbers come from the same source at
   both depths, so a quick and a full run of the same scenario compare
   on the operations both carry. Comparability is
   stricter than the frontmatter: reports whose `workload` differs are
   incomparable, and for drive-mode reports (and verifications or
   re-measures replaying one) so are runs whose recorded scenario or
   process identity (`instance`, `process_restarted`) differ — a driven
   session and a process-per-call run measure different things whatever
   the frontmatter says. A verification or re-measure and the report its
   `verifies` names replay the same scenario by construction and always
   compare — unless the benchmark the drive replays moved between them,
   which the verification's scenario record states: then only what the
   record says still compares (the load unchanged) does, and the rest
   is listed apart. List incomparable runs apart, never diff them.
   Stored numbers only — no live queries.
5. **Open telemetry gaps.** Gaps recorded in report bodies and not
   closed by a later verification ruling or instrumentation report —
   `closed` is the only closing ruling; a planned item ruled
   `present, unattributed` stays open. A
   quick report's `not queried (quick): ...` list is a statement about
   that mission, never a gap — do not count it; and a gap a quick
   verification lists as `not ruled (quick)` stays open, not closed.
   When gaps dominate a service's picture, the recommendation below
   should say instrument, not observe.
6. **Next recommended action** — the maturity principle operationalized,
   per service: a **verification is due** (service-relevant commits —
   step 2's rule — landed after the last report's `revision` and no
   verification covers them), a **new observation is due or overdue**
   (the cadence of past observation dates has lapsed, or recent verdicts
   keep churning), or the **loop can rest** (recent verification, stable
   verdicts, no unverified change). Every recommendation cites its
   inputs — dates, verdicts, revisions — evidence over impressions
   applies to the meta-loop too.

## A filter that matches nothing is still a status

When the caller restricted the status — service, stack, environment —
and no stored report matches, say exactly two things and stop:

- **what was searched**: each filter and its value, kept distinct (a
  stack scope is not an environment scope);
- **what exists instead**: the distinct services, stacks, and
  environments present across the stored frontmatters — the inventory
  of step 1, which is already read.

Example: "no report with environment `prod` — all 4 stored reports are
`environment: local`." That IS the status, not a failure: it names the
miss and hands back the values that let the caller correct the scope in
one turn.

Service names match **exactly** against the frontmatter `services`
values (and an instrumentation report's plan scope): a partial name
misses, and falls into the statement above rather than being guessed
into a match. Never render the unfiltered picture under a scope that
matched nothing, never render an empty table silently, and never error.

## Degrade gracefully

Degrade gracefully everywhere: a single report, reports predating newer
frontmatter fields, a body missing a structured section — render what
exists, mark what cannot be known ("no verification yet", "chain
unknown"), and never fail the whole status over one unreadable report.
The ledger degrades the same way: a malformed row, or one naming a
report or finding ID that does not exist, is **reported and skipped** —
say which row and why, then render the rest of the status. A broken
ledger row is never fatal, and never silently dropped either.
