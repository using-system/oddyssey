---
description: Investigate a service and author a k6 load-test benchmark plan as code in .odd/benchmarks/ - asks back whatever only a human can decide before dispatching the authoring agent, never executes the benchmark
---

Before dispatching anything: consult the `k6-guides` skill's
`authoring-inputs.md` reference for which dimensions of this benchmark
only a human can decide, and which the agent can discover on its own.
Ask the caller, **in this conversation, before any dispatch** - the
steps needing the caller cannot happen inside a subagent, the same
principle `/odd-observe`'s own preflight states outright. Specifically:

- **New benchmark, or an update to a named existing one** - if
  ambiguous, list what already exists for the named service (via
  `create-update-benchmark`'s recall) and ask.
- **Test type** - smoke / load / stress / soak / spike / breakpoint
  (`k6-guides`' `test-types.md` names what each answers).
- **Thresholds** - the pass/fail targets that matter.
- **Target base URL / environment** - never guessed by probing.
- **Load shape and duration** - propose a value informed by the test
  type and the service's known scale, then confirm it with the caller
  rather than silently deciding.

Never ask about anything `authoring-inputs.md` classifies as
agent-discoverable (target scope/endpoints) - that's the agent's job,
asking about it here would be litigating something the caller cannot
actually answer better than the codebase can.

Once every human-decided value is resolved, invoke the
`k6-benchmark-expert` agent. It owns the investigation method and the
authoring - this prompt only hands it a well-formed mission.

Build the mission from the arguments and the Q&A above:

- Arguments: $ARGUMENTS
- Expected fields (any order, free-form): the **service** to benchmark
  (required), **new or update** (default: ask if ambiguous, per above),
  **test type**, **thresholds**, **target base URL**, and optionally a
  **load shape/duration** the caller already has in mind (otherwise
  propose one during the Q&A above).

Close the mission with the `show-benchmark` skill: render its synthesis
of the stored benchmark as the final answer, stating the stored path.
The script and manifest - not the synthesis - are the input any future
run of this benchmark will use: never re-dump them in the conversation,
and never let the synthesis replace the stored files as that input.
