---
description: Investigate a codebase and get every input needed to plan OpenTelemetry instrumentation for it
---

Invoke the `otel-instrumentation-expert` agent. It owns the investigation
method and the report contract - this prompt only hands it a well-formed
mission.

Build the mission from the arguments below:

- `Skills: <directory>` - the `skills` line of the `package-layout`
  skill's `scripts/layout.py` - reachable because the preflight above
  already invoked a skill, and the host prints that skill's directory
  when it does: `package-layout` is its sibling. The script answers
  from its own location and is therefore exact wherever the package is
  installed. Run it once
  in the preflight and copy the line. Always carried, never guessed:
  the agent opens the skills' files there, by section, and an agent
  left to find them itself searches the repository and reads whatever
  it meets on the way.
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
