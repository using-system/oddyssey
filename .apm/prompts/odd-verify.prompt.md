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
  `.odd/otel-instrumentation-reports/`, or enough of a run name to find
  it in either directory - and, when that report's environment is
  remote, the access material the agent will need.
- Default when no report is named: the newest file across
  `.odd/observe-run-reports/` and `.odd/otel-instrumentation-reports/`
  (filenames sort chronologically - read frontmatters only, newest
  first). If the newest reports cover several services or span both
  kinds — observation and instrumentation, readable from the directory
  alone — ask which report is being verified before proceeding. If
  neither directory has a report, stop and say there is nothing to
  verify.
- When the resolved report is itself a verification (`mode: verify`,
  a `verifies` frontmatter field): follow `verifies` to the original
  report — observation or instrumentation — and verify against that one
  — a verify run always replays the report whose protocol was recorded,
  never a previous verification. When the resolved report is a verification by name or
  prose only (a pre-convention report with no `verifies` field), do not
  guess the original: ask the user to name the observation report to
  verify against before proceeding.

Preflight next - in the main conversation, before any dispatch: the
report's `environment` (`target` for an instrumentation report) is the
contract being replayed. When it disagrees
with the configured stack (`odd_config_get`), say so and **follow the
report** - a verify run replays the baseline's backend, never silently
retargets the current one (and it does not rewrite the configuration:
the divergence is stated, not persisted). Then run the
`check-backend-configuration` skill against the report's backend: show
the CLI's configuration, fail fast when it is not connected, and ask for
what is missing before dispatching.

Then build the mission block from that report:

- services and environment come from its frontmatter; mode is drive
  when the report records a scenario to replay, otherwise the
  frontmatter's mode. For an **instrumentation report** the frontmatter
  has no `services` or `mode`: the services are the ones its
  per-service plan names (summary table), the environment is its
  `target`, and the mode is drive - the verification protocol runs the
  services and exercises a scenario. Driving is self-authorized only on
  a local environment: when the report's environment is remote, ask the
  user for explicit confirmation before building a drive-mode mission -
  the agent will not drive a remote service without the caller saying
  so;
- baseline: the report itself - name its path and tell the agent to use
  it as the recalled baseline;
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
  directory;
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

Return the agent's report as-is: it carries the verdict and, stored in
`.odd/observe-run-reports/`, becomes the versioned record that the
fix - or the planned instrumentation - was measured, not assumed. Do
not summarize it away.
