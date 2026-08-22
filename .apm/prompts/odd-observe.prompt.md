---
description: Observe a running service through its telemetry (local stack or remote backend) and get the plan-ready observation report
---

Invoke the `observe-run` agent. It owns the whole method and the report
contract - this prompt only hands it a well-formed mission.

Build the mission block from the arguments below, applying the agent's own
defaults for every field not specified:

- Arguments: $ARGUMENTS
- Expected fields (any order, free-form): service name(s), environment
  (local by default, or the remote backend and its access material), mode
  (drive / observe / post-hoc), window, focus, baseline expectations.
- If no service name can be determined from the arguments, ask for it
  before invoking the agent.

Return the agent's report as-is: it is the deliverable the next
spec-driven wave consumes - do not summarize it away.
