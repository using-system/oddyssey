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

Preflight next - in the main conversation, before any dispatch, in
this order:

1. **The stack.** The report's `stack` is the contract being replayed -
   both report kinds, observation and instrumentation, name it
   `stack`. When it disagrees with the configured stack
   (`odd_config_get`), say so and **follow the report** - a verify run
   replays the baseline's stack, never silently retargets the current
   one (and it does not rewrite the configuration: the divergence is
   stated, not persisted).
2. **The execution mode, and the remote-drive question.** Resolve the
   mode - the mission block below restates the rule: the frontmatter's
   mode; for a `verify` or `re-measure` baseline, the mode of the
   report its `verifies` names; `drive` for an instrumentation report,
   whose frontmatter has no mode - never inferred from what the record
   contains. Driving is self-authorized only when the stack and the
   target are both local. When the resolved mode is `drive` and the
   report's `stack` is remote - whatever the report kind - ask the
   user for explicit confirmation before the CLI check, the k6 step,
   or any dispatch, naming what will be driven (the recorded
   scenario's commands; the stored benchmark the record names, with
   the revision the baseline recorded - the replay runs the current
   checkout; or, for an instrumentation report, the scenario its
   verification protocol names) and against which target. When that
   target is itself local (`localhost`) while the stack is remote, say
   so - the confirmation is then about the backend the run writes
   into; when the stack is local but the recorded target is remote,
   ask all the same - `observe-run`'s own rule keys on the service.
   The authorization the baseline run had was given for that run;
   `observe-run` drives a remote service only when the caller says so,
   this mission, and a stored report or manifest never carries a
   standing permission. A refusal ends the mission before anything is
   installed or checked: never downgrade the replay to `observe` on
   your own - that changes the protocol.
3. **The CLI.** Run the `backend-configuration` skill's `## Check` against the
   report's stack: show the CLI's configuration, stop where the skill
   stops, in its own words — the binary **not installed**: it offers
   the guided install and resumes once the binary exists, stopping only
   if the user declines, nothing dispatched meanwhile; or the
   connection proof failed, **"CLI not configured for <backend>"**:
   guidance, never an authentication on the user's behalf — and ask
   for what is missing before dispatching.
   Carry its closing `Preflight:` handoff block into the mission block
   verbatim — the agent reads the reference's other sections only (never
   the preflight's four: CLI binary, Setup, Configuration display,
   What to persist) and never re-proves what the preflight proved.
4. **k6.** When the replay will be `drive` with a stored benchmark (the
   report's record names one), ensure the `k6` binary is present, per
   the `k6-guides` skill's `install.md` auto-install step:
   `command -v k6`; when it is missing, run `brew install k6` directly
   when Homebrew is available (no confirmation - k6 needs no account
   and no configuration), otherwise follow that reference's
   non-interactive path for the platform or hand the remaining steps
   to the user and stop.
5. **The depth.** State it in the conversation before anything is
   dispatched, with the override in the same line: the baseline's
   `depth` when it has one; for an observation baseline without one,
   "this baseline predates the depth field — replaying `quick`; say
   `full verify` to replay at the protocol it ran"; for an
   instrumentation baseline, `full`. The mission-block rule below
   carries the detail.

Then build the mission block from that report:

- services and stack come from its frontmatter; the mode is the
  frontmatter's mode, **never inferred from whether the report records
  a scenario or a benchmark** — an `observe`-mode report backed by a
  stored benchmark records a replayable protocol nobody authorized
  this run to drive, so it replays as `observe` — and when the
  baseline is itself a verification or a re-measure (its frontmatter
  says `verify` or `re-measure`, neither an execution mode), the
  execution mode of the report **its** `verifies` names.
  For an **instrumentation report** the frontmatter has no `services` or
  `mode`: the services are the ones its per-service plan names (summary
  table), the stack is its frontmatter's `stack` all the same, and the
  mode is drive - the verification protocol runs the services and
  exercises a scenario;
- remote drive: the confirmation preflight step 2 obtained is what
  authorizes a `drive` mission on a remote stack - state in the
  mission block that it was given, and for what;
- baseline: the report itself - name its path and tell the agent to use
  it as the recalled baseline;
- baseline environment: hand the report's `environment` value over with
  it. The agent detects the environment of its own run, compares it
  against the one you handed over, and owns the hard stop when the two
  diverge - no verdict is ever ruled across environments. An
  **instrumentation report** carries no `environment` by design: say so
  in the mission block - the comparison is skipped and the environment
  the run detects is recorded fresh;
- depth: the baseline's `depth` frontmatter field is the mission's
  depth, no question asked. An **observation** baseline without one
  predates the field: it ran the full protocol (that is how every
  reader treats the absent field), but its replay runs `quick` — the
  cheap re-check is the point of the default — and you say so **in the
  conversation, before dispatch** (preflight step 5), then in the
  mission block, so the run record states the depth was defaulted. An
  **instrumentation** baseline has no `depth` because its contract has
  no such field: its presence rulings span every signal the plan
  names, so it replays at `full`. The arguments may force `full` or
  `quick` ("full verify", "quick check"): an argument wins over the
  field and the defaults. At `quick` depth the agent rules what its
  signals can rule and counts the rest as `not ruled (quick)`; a
  `full` replay of a `quick` baseline rules the baseline's checks and
  says its coverage was quick (the agent's Depth section);
- persistence: state that the run is a **verification** of that report,
  naming its exact filename, so the agent persists per the
  `observe-run-report` reference's verification rules (`odd-memory`) —
  `YYYY-MM-DD-HHmm-verify-<run_name>.md` (own timestamp, the baseline's
  run_name) with `mode: verify` and `verifies: <that exact filename>`
  (its repo-relative `.odd/otel-instrumentation-reports/<filename>`
  path when the baseline is an instrumentation report) in the
  frontmatter. The deliverable is an observation report in
  `.odd/observe-run-reports/` whatever the baseline's kind — the path
  shape is what says the baseline lives outside the observation
  directory. **Unless the replay tests no fix**: when the observed
  repo's code is unchanged since the baseline's `revision`, the
  mission is a **re-measure**, not a verification — same replay, but
  the agent persists `YYYY-MM-DD-HHmm-remeasure-<run_name>.md` with
  `mode: re-measure` and the same `verifies` field; calling it a
  verification would fabricate a fix that never existed. "Unchanged"
  means no change beyond the loop's own memory
  (`.odd/observe-run-reports/`, `.odd/otel-instrumentation-reports/`,
  `.odd/decisions.md`) and documentation, AND a clean working tree
  (uncommitted changes to anything else are changed code).
  `.odd/benchmarks/` is living source: a change to the benchmark the
  replay runs is a fix under test like any other code change (calling
  that a re-measure would deny a fix that happened); an unrelated
  benchmark's change is not this service's fix, and a record naming
  no benchmark has nothing to test there.

  Decide it before dispatching, from the baseline's `tree_anchor` and
  one tree read — no git walk while the anchor answers:

  ```text
  git ls-tree HEAD                                     # compare entry by entry with tree_anchor
  git status --porcelain                               # clean tree, or changed code
  git log <revision>..HEAD -- .odd/benchmarks/<name>/  # only when the record names a benchmark
  ```

  Ignore `.odd` (its hash moves with every report written) and every
  entry that cannot change the observed service's runtime behavior
  (documentation is the canonical case, but so are CI configuration,
  generated/packaging artifacts, and release-metadata files). Every
  runtime entry equal, a clean tree, no benchmark commit or change:
  **re-measure**. A runtime entry differing, a dirty tree, or a
  benchmark commit or change: **verification**. The git walk is the
  fallback only — a baseline with no `tree_anchor`, or a `revision`
  the benchmark command cannot resolve (a squash-merged clone), where
  the baseline report file's own commit date is the boundary and that
  commit sits inside the window (ignore it):

  ```text
  git rev-parse --verify <revision>^{commit}          # does the revision resolve?
  git log <revision>..HEAD -- <path>                  # yes: commits since it
  git log -1 --format=%cI -- <baseline report path>   # no: the report's own commit date
  git log --since=<that date> -- <path>               # is the boundary
  ```

  With no anchor, compare trees, not ancestry — a `git log` walk is
  misled by the rebased or squash-merged clone the anchor exists to
  survive — and with no `revision` either, that commit date is the
  substitute boundary — the same rule `/odd-status` applies. A
  differing entry you cannot classify makes the check undecidable,
  never a silent "code changed". When it is undecidable, or its
  outcome contradicts how the caller framed the mission — they asked
  to *verify* but nothing changed, or they said *re-measure* but
  commits landed — say so and ask which of the two the mission is,
  never silently reclassify. Say which one it is in the mission
  block. When what changed is the
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
  query and rule **closed / present, unattributed / still missing**,
  with the query as evidence: `closed` only when the signal carries
  the run's identity (the agent's attribution rule) - a signal from an
  unidentified process is present, unattributed, never closed. A
  protocol written before that rule names no attribution evidence:
  the run supplies its own (the service driven with the run slug and
  the profiler tag) and the report says the protocol predated the
  rule. On a remote drive, the identity is header-borne
  (`run-scenario` step 0: the run's User-Agent and a `traceparent`
  whose trace id carries the protocol's prefix, a part derived from
  **this run's slug**, and the sequence) - a new slug every replay,
  and when the baseline's ids carried no run part, the replay adopts
  the run-unique form and says so: the prefix selectors still match,
  the requests do not change, only the ids do. An empty result
  follows the same query-suspect rule as
  below: prove the query sound before ruling "still missing". A
  protocol query that projects a credential-bearing field is replayed
  without that field and ruled on what remains, and the ruling says
  so (the agent's rule) - the value never reaches the report;
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

Close the mission with the `## Show` of `odd-memory`'s
`observe-run-report` reference: render its
synthesis from the persistence return value the agent's reply carries
(stored path, carrying commit, the synthesis block) as the final
answer - the verdict-first headline leads, stating the stored path; no
re-read of the file just written. The report file, stored in
`.odd/observe-run-reports/`, remains the versioned record that the
fix - or the planned instrumentation - was measured, not assumed:
never re-dump the raw report in the conversation, and never let the
synthesis replace the stored file as that record.
