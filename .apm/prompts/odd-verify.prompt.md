---
description: Verify that a fix or an implemented instrumentation plan landed - replay a stored report's protocol (observation or instrumentation report) and get the full observation report, carrying the verdict on everything it recorded - measurements, anomalies, telemetry gaps, or planned signals now present
---

Invoke the `observe-run` agent. It owns the whole method and the report
contract - this prompt only hands it a verification mission built from a
stored report: an **observation report** (before/after measurements) or
an **instrumentation report** (presence rulings on planned signals).

Resolve the report first:

- Arguments: $ARGUMENTS
- Expected fields (any order, free-form): the report to verify against -
  a path under `.odd/observe-run-reports/` or
  `.odd/otel-instrumentation-reports/`, enough of a run name to find
  it in either directory, or constraints that scope the newest-first
  resolution below ("my last report for checkout", "my last prod
  report" - a service, a stack, or a deployment environment, matched
  against the stored frontmatters) - and, when that report's stack is
  remote, the access material the agent will need.
- Default when no report is named: the newest file across
  `.odd/observe-run-reports/` and `.odd/otel-instrumentation-reports/`
  (filenames sort chronologically - read frontmatters only, newest
  first). If the newest reports cover several services or span both
  kinds — observation and instrumentation, readable from the directory
  alone — ask which report is being verified before proceeding. If
  neither directory has a report, stop and say there is nothing to
  verify.
- When the resolved report is itself a verification or a re-measure
  (`mode: verify` or `mode: re-measure`, a `verifies` frontmatter
  field): follow `verifies` **exactly one hop** — the report it names
  is the protocol source and the baseline to verify against. That
  report is usually the original observation or instrumentation
  report; it may itself be a verification whose own §7 measurement
  protocol was the one replayed — then that verification is the
  baseline, and the new report's `verifies` names it. Never chase the
  chain further: the reference always names the protocol's actual
  source, one hop away. One carve-out: when the caller explicitly
  targets a verification report's **own** §7 protocol, there is no
  hop — that verification is the baseline, and the new report's
  `verifies` names it (this is how the first `verifies: <verification>`
  reference comes to exist).
  When the resolved report is a verification by name or
  prose only (a pre-convention report with no `verifies` field), do not
  guess the original: ask the user to name the observation report to
  verify against before proceeding.

Preflight next - in the main conversation, before any dispatch: the
report's `stack` is the contract being replayed - both report kinds,
observation and instrumentation, name it `stack`. When it disagrees
with the configured stack (`odd_config_get`), say so and **follow the
report** - a verify run replays the baseline's stack, never silently
retargets the current one (and it does not rewrite the configuration:
the divergence is stated, not persisted). Then run the
`check-backend-configuration` skill against the report's stack: show
the CLI's configuration, fail fast when it is not connected, and ask for
what is missing before dispatching. When the replay will be `drive`
with a stored benchmark (the report's record names one), ensure the
`k6` binary is present, per the `k6-guides` skill's `install.md`
auto-install step: `command -v k6`; when it is missing, run
`brew install k6` directly when Homebrew is available (no confirmation
- k6 needs no account and no configuration), otherwise follow that
reference's non-interactive path for the platform or hand the
remaining steps to the user and stop.

Then build the mission block from that report:

- services and stack come from its frontmatter; the mode is the
  frontmatter's mode, **never inferred from whether the report records
  a scenario or a benchmark** — an `observe`-mode report backed by a
  stored benchmark records a replayable protocol nobody authorized
  this run to drive, so it replays as `observe` — and when the
  baseline is itself a verification (its frontmatter says `verify`,
  which is no execution mode), the execution mode of the report
  **its** `verifies` names.
  For an **instrumentation report** the frontmatter has no `services` or
  `mode`: the services are the ones its per-service plan names (summary
  table), the stack is its frontmatter's `stack` all the same, and the
  mode is drive - the verification protocol runs the services and
  exercises a scenario. Driving is self-authorized only on the local
  stack: when the report's stack is remote, ask the user for explicit
  confirmation before building a drive-mode mission - the agent will not
  drive a remote service without the caller saying so;
- baseline: the report itself - name its path and tell the agent to use
  it as the recalled baseline;
- baseline environment: hand the report's `environment` value over with
  it. The agent detects the environment of its own run, compares it
  against the one you handed over, and owns the hard stop when the two
  diverge - no verdict is ever ruled across environments. An
  **instrumentation report** carries no `environment` by design: say so
  in the mission block - the comparison is skipped and the environment
  the run detects is recorded fresh;
- persistence: state that the run is a **verification** of that report,
  naming its exact filename, so the agent persists per the
  `create-observe-run-report` skill's verification rules —
  `YYYY-MM-DD-HHmm-verify-<run_name>.md` (own timestamp, the baseline's
  run_name) with `mode: verify` and `verifies: <that exact filename>`
  (its repo-relative `.odd/otel-instrumentation-reports/<filename>`
  path when the baseline is an instrumentation report) in the
  frontmatter. The deliverable is an observation report in
  `.odd/observe-run-reports/` whatever the baseline's kind — the path
  shape is what says the baseline lives outside the observation
  directory. **Unless the replay tests no fix**: when the observed
  repo's code is unchanged since the baseline's `revision` — no
  commits beyond the loop's own memory and documentation AND a clean
  working tree (uncommitted changes to anything else are changed
  code) — the mission is a **re-measure**, not a verification: same
  replay, but the agent persists
  `YYYY-MM-DD-HHmm-remeasure-<run_name>.md` with `mode: re-measure`
  and the same `verifies` field — calling it a
  verification would fabricate a fix that never existed. The loop's
  memory is the append-only report stores and the ledger —
  `.odd/observe-run-reports/`, `.odd/otel-instrumentation-reports/`,
  `.odd/decisions.md` — and nothing else under `.odd/`:
  `.odd/benchmarks/` is living source, and the benchmark the replay
  runs, when its script or manifest changed since the baseline, is
  changed code like any other path (a drive replay runs it, so a fix
  to it is a fix under test — calling that a re-measure would deny a
  fix that
  happened). Check before dispatching; the preferred boundary is the
  baseline's `tree_anchor`: compare its entry hashes against
  `git ls-tree HEAD`, ignoring `.odd` (its top-level hash moves with
  every report written) and every entry that cannot change the
  observed service's runtime behavior (documentation is the canonical
  case, but so are CI configuration, generated/packaging artifacts,
  and release-metadata files) — resolvable in any clone whatever the
  merge strategy. Then test the benchmark by path, anchor or not: the
  path is the benchmark the baseline's scenario record names
  (`.odd/benchmarks/<name>/`); when the record names none, there is
  nothing to test — a benchmark the replay does not run cannot be its
  fix, and an unrelated benchmark's update is not this service's
  fix. Commits touching that path since the baseline, or uncommitted
  changes under it, are changed code. When the revision does not
  resolve (a squash-merged clone), the boundary is the baseline report
  file's own commit date, and that commit sits inside the window —
  ignore it:

  ```text
  git rev-parse --verify <revision>^{commit}          # does the revision resolve?
  git log <revision>..HEAD -- <path>                  # yes: commits since it
  git log -1 --format=%cI -- <baseline report path>   # no: the report's own commit date
  git log --since=<that date> -- <path>               # is the boundary
  ```

  Differing entries you cannot classify make the check undecidable
  (the rule below), never a silent "code changed". With no anchor,
  compare trees, not ancestry, and when the baseline carries no
  `revision` either, the report's own commit date (the same command
  as above) is the substitute boundary — the same rule `/odd-status`
  applies. When the check is still undecidable, or its outcome
  contradicts how
  the caller framed the mission — they asked to *verify* but nothing
  changed, or they said *re-measure* but commits landed — say so and
  ask which of the two the mission is, never silently reclassify. Say
  which one it is in the mission block. When what changed is the
  benchmark a drive replay runs, say that too: the agent rules the
  baseline's findings against the benchmark itself (a script defect,
  an unattainable threshold) on the new revision, and compares the
  service's before/after numbers only when the load did not change
  (same requests, pacing, and stages) — otherwise it says so, rules
  what it can, and its numbers open the service's new baseline;
- focus, **instrumentation baseline**: not before/after measurements
  but **presence rulings**. For every item the report's verification
  protocol and per-service plan recorded - planned spans searchable per
  service, each planned metric present, logs carrying trace IDs,
  resource attributes set - prove it now exists with the discovery
  query and rule **closed / still missing**, with the query as
  evidence. An empty result follows the same query-suspect rule as
  below: prove the query sound before ruling "still missing";
- focus, **observation baseline** (today's behavior, unchanged): verify
  everything the report recorded - replay its recorded scenario
  verbatim when it has one (otherwise observe a comparable window in
  the report's mode), then rule on each item with its evidence:
  - every verification check of its measurement protocol: before-value,
    after-value, recorded pass criterion, pass/fail. An empty or NaN
    after-value is a **query-suspect** outcome, not a failure: first
    doubt the recorded query (evaluate at several times, read the raw
    series behind it, try an equivalent form), especially when the
    check is marked `not validated`, and only rule "fix did not land"
    once the query itself is proven sound. When the query was the
    problem, reporting its corrected form is part of the verdict;
  - every anomaly it found: fixed, still present, or worse, with the
    query that proves it;
  - every telemetry gap it listed: now filled or still missing, with the
    discovery query.

Close the mission with the `show-observe-run-report` skill: render its
synthesis of the stored report as the final answer - the verdict-first
headline leads, stating the stored path. The report file, stored in
`.odd/observe-run-reports/`, remains the versioned record that the
fix - or the planned instrumentation - was measured, not assumed:
never re-dump the raw report in the conversation, and never let the
synthesis replace the stored file as that record.
