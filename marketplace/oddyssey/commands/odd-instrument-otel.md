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
  intended export stack (default: the local one).

Close the mission with the `## Show` of `odd-memory`'s
`otel-instrumentation-report` reference:
render its synthesis of the stored report as the final answer, stating
the stored path. The report file - not the synthesis - is the input
the spec-driven instrumentation plan is built from: never re-dump the
raw report in the conversation, and never let the synthesis replace
the stored file as the plan's input.
