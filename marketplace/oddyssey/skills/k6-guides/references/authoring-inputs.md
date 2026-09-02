# What a benchmark's authoring needs decided

Not a k6 how-to page - a synthesis for `/odd-instrument-bench` and
`k6-benchmark-expert`: every dimension a k6 benchmark structurally needs
decided before it can be written, and who can answer it.

| Dimension | Who decides | Why |
| --- | --- | --- |
| New benchmark, or update to a named existing one | human | intent - the agent can list what exists for the service but not choose |
| Test type (smoke / load / stress / soak / spike / breakpoint) | human | encodes what the caller wants to learn (see test-types.md) |
| Thresholds (the pass/fail targets) | human | a target is a product decision, not a measurement - but whether the service can structurally meet it (a fixed sleep, a rate limit, an injected error rate) is a fact the investigation already holds, so the agent cross-checks each threshold against the floors it finds and hands an unattainable one back, with the evidence, before persisting; the caller raises, drops, re-scopes, or keeps it with the floor acknowledged |
| Load shape, executor, and pacing | agent proposes, human confirms | follows mechanically from the test type, but concurrency changes every latency number and pacing sets the request rate the VU count alone does not (see scripting.md) - state them explicitly |
| Target scope (which endpoints/operations) | agent | discoverable: routes, OpenAPI, hot operations in stored `.odd/` reports |
| Duration and stage lengths | agent proposes, human confirms | the type's documented range is discoverable; the actual time budget is the caller's |
| Target base URL / environment | human | mission-time input, never guessed by probing |
| One-iteration smoke at the target before persisting | human (remote target only; a local target is self-authorized) | one real pass over the script's requests, with real side effects, on someone's environment - the caller says yes each time, at mission time, never as a stored standing permission (see running-tests.md, "Validating without running") |

**This is the whole contract**: `/odd-instrument-bench` asks about every
row marked "human" (and confirms the "agent proposes, human confirms"
rows) **before** dispatching `k6-benchmark-expert` - never inside the
agent, where going back and forth with the caller gets a lot harder.
The agent then investigates and decides every "agent" row on its own.

Every dimension above appears exactly once, classified. If a future
edit adds a dimension, it goes in this table with a "who decides"
value - an unclassified dimension is exactly the kind of gap this file
exists to prevent.
