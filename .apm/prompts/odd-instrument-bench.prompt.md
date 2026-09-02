---
description: Investigate a service and author a k6 load-test benchmark plan as code in .odd/benchmarks/ - asks back whatever only a human can decide before dispatching the authoring agent, which validates the script with k6 inspect and one smoke iteration and never runs the benchmark
---

Before dispatching anything: ensure the `k6` binary is present, per
the `k6-guides` skill's `install.md` auto-install step - authoring
validates the script with `k6 inspect` and a one-iteration smoke, both
need it. `command -v k6`; when it is missing, run `brew install k6`
directly when Homebrew is available (no confirmation - k6 needs no
account and no configuration), otherwise follow that reference's
non-interactive path for the platform or hand the remaining steps to
the user and stop. Then consult the
`k6-guides` skill's `authoring-inputs.md` reference for which
dimensions of this benchmark only a human can decide, and which the
agent can discover on its own.
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
- **Load shape, pacing, and duration** - propose a value informed by the
  test type and the service's known scale, then confirm it with the
  caller rather than silently deciding (VU count alone is not the request
  rate - the pacing belongs in what gets confirmed).
- **Smoke check at a remote target** - when the target base URL is not
  local (`localhost`, `127.0.0.1`), ask whether one iteration of the
  script may be sent at it before persisting: one real pass over the
  script's requests, with real side effects, and nothing more. A local
  target is self-authorized, no question. A refusal is passed to the
  agent as `declined`, never silently turned into a yes.

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
  **test type**, **thresholds**, **target base URL**, the **smoke
  check** authorization for a remote target (asked above), and
  optionally a **load shape/duration** the caller already has in mind
  (otherwise propose one during the Q&A above).

Close the mission with the `show-benchmark` skill: render its synthesis
of the stored benchmark as the final answer, stating the stored path.
The script and manifest - not the synthesis - are the input any future
run of this benchmark will use: never re-dump them in the conversation,
and never let the synthesis replace the stored files as that input.
