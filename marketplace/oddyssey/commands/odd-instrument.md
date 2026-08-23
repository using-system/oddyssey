---
description: Investigate a codebase and get every input needed to plan OpenTelemetry instrumentation for it
---

Invoke the `otel-instrumentation-expert` agent. It owns the investigation
method and the report contract - this prompt only hands it a well-formed
mission.

Build the mission from the arguments below:

- Arguments: $ARGUMENTS
- Expected fields (any order, free-form): the path or repository to
  investigate (default: the current repository), and optionally the
  intended export target (default: the local oddyssey stack).

Return the agent's report as-is: it is the input the spec-driven
instrumentation plan is built from - do not summarize it away.
