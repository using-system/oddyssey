---
description: Verify that a fix landed - replay a stored observation report's protocol and get the full observation report, carrying the before/after verdict on everything it recorded - measurements, anomalies, telemetry gaps
---

Invoke the `observe-run` agent. It owns the whole method and the report
contract - this prompt only hands it a verification mission built from a
stored observation report.

Resolve the report first:

- Arguments: $ARGUMENTS
- Expected fields (any order, free-form): the report to verify against -
  a path under `.odd/observe-run-reports/` or enough of a run name to
  find it - and, when that report's environment is remote, the access
  material the agent will need.
- Default when no report is named: the newest file in
  `.odd/observe-run-reports/` (filenames sort chronologically - read
  frontmatters only, newest first). If the newest reports cover several
  services, ask which one is being verified before proceeding. If the
  directory has no report, stop and say there is nothing to verify.
- When the resolved report is itself a verification (`mode: verify`,
  a `verifies` frontmatter field): follow `verifies` to the original
  observation report and verify against that one — a verify run always
  replays the report whose protocol was recorded, never a previous
  verification. When the resolved report is a verification by name or
  prose only (a pre-convention report with no `verifies` field), do not
  guess the original: ask the user to name the observation report to
  verify against before proceeding.

Preflight next - in the main conversation, before any dispatch: the
report's `environment` is the contract being replayed. When it disagrees
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
  frontmatter's mode. Driving is self-authorized only on a local
  environment: when the report's environment is remote, ask the user
  for explicit confirmation before building a drive-mode mission - the
  agent will not drive a remote service without the caller saying so;
- baseline: the report itself - name its path and tell the agent to use
  it as the recalled baseline;
- persistence: state that the run is a **verification** of that report,
  naming its exact filename, so the agent persists per the
  `create-observe-run-report` skill's verification rules —
  `YYYY-MM-DD-HHmm-verify-<run_name>.md` (own timestamp, the baseline's
  run_name) with `mode: verify` and `verifies: <that exact filename>`
  in the frontmatter;
- focus: verify everything the report recorded - replay its recorded
  scenario verbatim when it has one (otherwise observe a comparable
  window in the report's mode), then rule on each item with its
  evidence:
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
`.odd/observe-run-reports/`, becomes the versioned record that the fix
was measured - do not summarize it away.
