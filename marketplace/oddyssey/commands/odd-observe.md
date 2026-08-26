---
description: Observe a running service through its telemetry (local stack or remote backend) and get the plan-ready observation report
---

Invoke the `observe-run` agent. It owns the whole method and the report
contract - this prompt only hands it a well-formed mission.

Preflight first - in the main conversation, before any dispatch (the
steps needing the user cannot happen inside a subagent):

1. Resolve the target stack: the configured one (`odd_config_get`), or
   the one the arguments name - in which case persist the switch with
   `odd_config_set` so the next run starts from it. A local mission on a
   non-local stack switches to `local` - the local stack is self-serve,
   nothing to authenticate; every other value names a remote backend
   (for `grafana`, the gcx context says which instance).
2. Run the `check-backend-configuration` skill: show the CLI's effective
   configuration to the user (no confirmation needed), and fail fast
   with its "CLI not configured for <backend>" error instead of letting
   the agent attempt interactive auth. Ask for whatever the mission
   still needs (instance URL, tenant, access material by name) before
   dispatching.

Build the mission block from the arguments below, applying the agent's own
defaults for every field not specified:

- Arguments: $ARGUMENTS
- Expected fields (any order, free-form): service name(s), stack
  (defaults to the configured one - the preflight resolved it), mode
  (drive / observe / post-hoc), window, focus, baseline expectations.
- The deployment environment is not a mission field: the agent detects
  it from the telemetry (`deployment.environment.name`) and records it -
  never pass one, never guess one here.
- If no service name can be determined from the arguments, ask for it
  before invoking the agent.

Return the agent's report as-is: it is the deliverable the next
spec-driven wave consumes - do not summarize it away.
