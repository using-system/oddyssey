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
  find it (default: the latest report, located per the
  `create-observe-run-report` skill's recall procedure). If the
  directory has no report, stop and say there is nothing to verify.

Then build the mission block from that report:

- services, environment, and mode come from its frontmatter and its
  section 7 (drive mode when the protocol records a scenario to replay);
- baseline: the report itself - name its path;
- focus: verify everything the report recorded - replay the recorded
  scenario verbatim, then rule on each item with its evidence:
  - every verification check of its measurement protocol: before-value,
    after-value, recorded pass criterion, pass/fail;
  - every anomaly it found: fixed, still present, or worse, with the
    query that proves it;
  - every telemetry gap it listed: now filled or still missing, with the
    discovery query.

Return the agent's report as-is: it carries the verdict and, stored in
`.odd/observe-run-reports/`, becomes the versioned record that the fix
was measured - do not summarize it away.
