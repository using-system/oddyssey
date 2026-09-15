---
description: Investigate a codebase and get every input needed to plan OpenTelemetry instrumentation for it
argument-hint: "[path or repo] [export stack] [context]"
---

Invoke the `otel-instrumentation-expert` agent. It owns the investigation
method and the report contract - this prompt only hands it a well-formed
mission.

Build the mission from the arguments below:

- `Skills: <directory>` - the `skills` line of the `package-layout`
  skill's `scripts/layout.py`. This prompt invokes no skill before
  dispatching, so when this session has invoked none of them yet,
  invoke `package-layout` once - the host prints the skill's directory
  when it does, and the script is inside it. The script answers from
  its own location and is therefore exact wherever the package is
  installed. Run it once
  in the preflight and copy the line. Always carried, never guessed:
  the agent opens the skills' files there, by section, and an agent
  left to find them itself searches the repository and reads whatever
  it meets on the way.
- Arguments: $ARGUMENTS
- Expected fields (any order, free-form): the path or repository to
  investigate (default: the current repository), and optionally the
  intended export stack (default: the local one).

Close the mission with the synthesis the `odd-memory` skill's report
script renders from the stored file - the agent's reply carries the
stored path:

```bash
python3 <Skills>/odd-memory/scripts/odd_report.py show <stored path>
```

Run it - that is its whole surface - and render its output as the final
answer, in the conversation's language, stating the stored path. The
report file - not the synthesis - is the input the spec-driven
instrumentation plan is built from: never re-dump
the raw report in the conversation, and never let the synthesis replace
the stored file as the plan's input.
