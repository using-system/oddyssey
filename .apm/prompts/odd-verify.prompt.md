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
  material the agent will need (or confirmation the backend CLI is
  already configured).
- Default when no report is named: the newest file in
  `.odd/observe-run-reports/` (filenames sort chronologically - read
  frontmatters only, newest first). If the newest reports cover several
  services, ask which one is being verified before proceeding. If the
  directory has no report, stop and say there is nothing to verify.

Then build the mission block from that report:

- services and environment come from its frontmatter; mode is drive
  when the report records a scenario to replay, otherwise the
  frontmatter's mode. Driving is self-authorized only on a local
  environment: when the report's environment is remote, ask the user
  for explicit confirmation before building a drive-mode mission - the
  agent will not drive a remote service without the caller saying so;
- baseline: the report itself - name its path and tell the agent to use
  it as the recalled baseline;
- focus: verify everything the report recorded - replay its recorded
  scenario verbatim when it has one (otherwise observe a comparable
  window in the report's mode), then rule on each item with its
  evidence:
  - every verification check of its measurement protocol: before-value,
    after-value, recorded pass criterion, pass/fail. An empty or NaN
    after-value is a **query-suspect** outcome, not a failure: first
    doubt the recorded query (evaluate at several times, read the raw
    series behind it, try an equivalent form) — especially when the
    check is marked `not validated` — and only rule "fix did not land"
    once the query itself is proven sound. When the query was the
    problem, reporting its corrected form is part of the verdict;
  - every anomaly it found: fixed, still present, or worse, with the
    query that proves it;
  - every telemetry gap it listed: now filled or still missing, with the
    discovery query.

Return the agent's report as-is: it carries the verdict and, stored in
`.odd/observe-run-reports/`, becomes the versioned record that the fix
was measured - do not summarize it away.
