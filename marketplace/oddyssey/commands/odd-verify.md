---
description: Verify that a fix or an implemented instrumentation plan landed - replay a stored report's protocol (observation or instrumentation report) and get the full observation report, carrying the verdict on everything it recorded - measurements, anomalies, telemetry gaps, or planned signals now present
argument-hint: "[<report path> | my last <service | env | stack> report] [full | quick]"
---

Invoke the `observe-run` agent. It owns the whole method and the report
contract - this prompt only hands it a verification mission built from a
stored report: an **observation report** (before/after measurements) or
an **instrumentation report** (presence rulings on planned signals).

- Arguments: $ARGUMENTS
- Expected fields (any order, free-form): the report to verify against -
  a path under `.odd/observe-run-reports/` or
  `.odd/otel-instrumentation-reports/`, enough of a run name to find
  it, or constraints on the newest-first resolution ("my last report
  for checkout", "my last prod report", "my last report on seq": a
  service, a deployment environment, a stack) - a depth ("full
  verify", "quick check"), the carve-out "verify that verification's
  own protocol", how the caller frames the mission (a verification, or
  "nothing changed, re-measure"), and, when the report's stack is
  remote, the access material the agent will need.

**Resolve the baseline first**, with the `odd-memory` skill's
`observe-run-report` reference, `## Resolving a replay` - its
`baseline` command, the arguments' report, constraints and depth passed
as flags, nothing else. It settles what the inputs fix: the resolved
report, the baseline one hop away (or none under the carve-out), the
`verifies` value, the services, the stack, the environment, the
execution mode the `verifies` chain reaches, the depth and its reason,
the revision, the benchmark the record names, the recorded target, and
whether a drive needs the user's confirmation. An `ask:` line is a
question only the user can answer - which report, which original,
which mode - put it to them verbatim and stop until they answer; never
guess past it. `nothing to verify` ends the mission.

Preflight next - in the main conversation, before any dispatch, in
this order:

1. **The stack.** The `stack` line is the contract being replayed.
   When it disagrees with the configured stack (`odd_config_get`),
   say so and **follow the report** - a verify run replays the
   baseline's stack, never silently retargets the current one, and
   never rewrites the configuration: the divergence is stated, not
   persisted. That `stack` may be a custom name - a value on no row of
   `builtin-stacks.md`: step 3's `## Check` resolves it from
   `.odd/observability-stacks/<name>/guide.md` in this clone and, when
   that directory is absent, stops with the `observability-stack`
   reference's error - carry that stop: the report's contract cannot
   be replayed from a guess, and never from the configured stack
   instead.
2. **The remote-drive question.** When the `drive confirmation` line
   says `required`, ask the user for explicit confirmation before the
   CLI check, the k6 step, or any dispatch, naming what will be driven
   (the recorded scenario's commands; the stored benchmark the record
   names, with the revision the baseline recorded - the replay runs
   the current checkout; or, for an instrumentation report, the
   scenario its verification protocol names) and against which target
   - the line says which of the two, the stack or the recorded target,
   is not local. The authorization the baseline run had was given for
   that run; `observe-run` drives a remote service only when the
   caller says so, this mission, and a stored report or manifest never
   carries a standing permission. A refusal ends the mission before
   anything is installed or checked: never downgrade the replay to
   `observe` on your own - that changes the protocol.
3. **The CLI.** Run the `backend-configuration` skill's `## Check`
   against the report's stack: show the CLI's configuration, stop
   where the skill stops, in its own words - the binary **not
   installed**: it offers the guided install and resumes once the
   binary exists, stopping only if the user declines, nothing
   dispatched meanwhile; or the connection proof failed, **"CLI not
   configured for <backend>"**: guidance, never an authentication on
   the user's behalf - and ask for what is missing before dispatching.
   Carry its closing `Preflight:` handoff block into the mission block
   verbatim - the agent reads the reference's other sections only
   (never the preflight's four: CLI binary, Setup, Configuration
   display, What to persist) and never re-proves what the preflight
   proved.
4. **k6.** When the mode is `drive` and the `benchmark` line names one,
   ensure the `k6` binary is present, per the `k6-guides` skill's
   `install.md` auto-install step: the preflight script's `k6=` line
   already says whether it is there; when it reported it missing, run
   `brew install k6` directly when Homebrew is available (no
   confirmation - k6 needs no account and no configuration), otherwise
   follow that reference's non-interactive path for the platform or
   hand the remaining steps to the user and stop.
5. **The depth.** State the `depth` line in the conversation, reason
   included, before anything is dispatched - the run record must say
   when the depth was defaulted.
6. **Verification or re-measure.** The same reference's `boundary`
   command on the baseline: `verification` when a runtime entry, an
   uncommitted change to one, or the benchmark the record names moved
   since the baseline's revision - the mission tests a fix;
   `re-measure` when nothing did - calling it a verification would
   fabricate a fix that never existed; `undecidable` with what it
   could not settle - an entry never ruled runtime or not: rule it
   with the user (`/odd-status "<entry> is runtime | non-runtime"`
   records the ruling for good; `--runtime` / `--non-runtime` holds
   for this run) and run it again; an entry present on one side only,
   which no ruling settles, or an `ask:` line (nothing fixes the
   boundary): ask the user which of the two the mission is - never
   read either as "code changed". When its outcome contradicts how
   the caller framed the mission - they asked to *verify* but nothing
   changed, they said *re-measure* but commits landed - say so and ask
   which of the two the mission is, never silently reclassify. When what
   changed is the benchmark a drive replay runs, say that too: the
   agent rules the baseline's findings against the benchmark itself
   (a script defect, an unattainable threshold) on the new revision,
   and compares the service's before/after numbers only when the load
   did not change (same requests, pacing, and stages) - otherwise it
   says so, rules what it can, and its numbers open the service's new
   baseline.

Then build the mission block:

- `Skills: <directory>` - **not from the report**, whose path was a
  different machine's: the `skills` line of the `package-layout`
  skill's `scripts/layout.py` - reachable because the preflight above
  already invoked a skill, and the host prints that skill's directory
  when it does: `package-layout` is its sibling. The script answers
  from its own location and is therefore exact wherever the package is
  installed. Run it once in the preflight and copy the line. Always
  carried, never guessed: the agent opens the skills' files there, by
  section, and an agent left to find them itself searches the
  repository and reads whatever it meets on the way.
- the `baseline` command's lines, copied: the services, the stack, the
  mode (never inferred from whether the report records a scenario or a
  benchmark - an `observe`-mode report backed by a stored benchmark
  records a replayable protocol nobody authorized this run to drive),
  the depth, the benchmark when one is named, the baseline's path -
  the agent uses it as the recalled baseline - and its environment:
  the agent detects the environment of its own run, compares it
  against the one handed over, and owns the hard stop when the two
  diverge - no verdict is ever ruled across environments; an
  instrumentation baseline carries none, say so - the comparison is
  skipped and the environment the run detects is recorded fresh;
- remote drive: the confirmation step 2 obtained is what authorizes a
  `drive` mission on a remote stack - state that it was given, and for
  what;
- verification or re-measure, from step 6, with what changed; the run
  persists through the reference's `new --mode verify` (or `--mode
  re-measure`) `--verifies <the verifies line>` - the script names the
  file and writes the frontmatter, this block restates none of it;
  the deliverable is an observation report in
  `.odd/observe-run-reports/` whatever the baseline's kind;
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
  (`run-scenario`'s `run-identity.md`: the run's User-Agent and a
  `traceparent` whose trace id carries the protocol's prefix, a part
  derived from **this run's slug**, and the sequence) - a new slug
  every replay, and when the baseline's ids carried no run part, the
  replay adopts the run-unique form and says so: the prefix selectors
  still match, the requests do not change, only the ids do. An empty
  result follows the same query-suspect rule as below: prove the query
  sound before ruling "still missing" - and a health check on a
  Collector component ("zero error lines mentioning it") is ruled
  under the component id as configured, read from the configuration
  the plan changed, once the grep is proven able to match (the agent's
  rule): a name that matches nothing on the whole history closes
  nothing. A protocol query that projects a credential-bearing field
  is replayed without that field and ruled on what remains, and the
  ruling says so (the agent's rule) - the value never reaches the
  report;
- focus, **observation baseline**: verify everything the report
  recorded - replay its recorded scenario verbatim when it has one
  (otherwise observe a comparable window in the report's mode), then
  rule on each item with its evidence:
  - every verification check of its measurement protocol: before-value,
    after-value, recorded pass criterion, pass/fail. An empty or NaN
    after-value is a **query-suspect** outcome, not a failure: first
    doubt the recorded query (evaluate at several times, read the raw
    series behind it, try an equivalent form), especially when the
    check is marked `not validated` or `validated: before-shape` only
    (a validation note naming no shape reads as before-shape) - a
    "reaches zero" check authored on populated data may drop the
    zero rows it measures (a join aggregated without `coalesce`, a
    ratio over an absent series) - and only rule "fix did not land"
    once the query itself is proven sound. When the query was the
    problem, reporting its corrected form is part of the verdict, and
    the report's protocol carries the corrected form for the next
    replay;
  - every anomaly it found: fixed, still present, or worse, with the
    query that proves it;
  - every telemetry gap it listed: now filled or still missing, with the
    discovery query.

Close the mission by running
`python3 <Skills>/odd-memory/scripts/odd_report.py show <the stored path the agent's reply carries>`
(its whole surface) and printing the rendering as the final answer,
translated to the conversation's language - on a custom stack its
stack-friction count and entries are part of the rendering. The report
file, stored in `.odd/observe-run-reports/`, remains the versioned
record that the fix - or the planned instrumentation - was measured,
not assumed: never re-dump the raw report in the conversation, and
never let the synthesis replace the stored file as that record.
