---
description: Author a custom observability stack as a directory in .odd/observability-stacks/ - guide.md plus the query scripts it names, verified live against the backend - through the stack-instrumentation-expert agent; also completes one from an instruction, links one another repository carries, and fixes one from the stack-friction section of an observation report
argument-hint: "create a stack <name> [from <URL or path>] [: <instructions>] | for stack <name>: <instructions> | create a stack <name> linked to <URL, or repository and path> | from report <path> [for stack <name>]"
---

A backend the package does not ship becomes a **custom stack**: a
directory in the observed repository,
`.odd/observability-stacks/<name>/`, holding `guide.md` — the same
sections as a built-in reference — and `scripts/`, the query scripts
the guide names, so a run against it composes nothing a built-in stack
ships. Writing one is an expert's work — research, scripts, live
verification, the memory contract — and this prompt does what needs
the user, then hands the rest to the `stack-instrumentation-expert`
agent, the way `/odd-instrument-bench` hands authoring to
`k6-benchmark-expert`. `/odd-config` displays, switches and persists;
it never writes a stack.

Before dispatching anything, resolve the four things only this
conversation can:

- **The shape**, from the arguments — one of:
  - **create** — `create a stack <name>`, with the sources the user
    gave: a URL or a local path after `from`, and instructions after a
    colon;
  - **complete** — `for stack <name>: <instructions>` (or a create
    request naming a stack that already exists): the sections or the
    scripts the instructions touch, and only those;
  - **link** — `create a stack <name> linked to <URL, or repository
    and path>`: the pointer only, a guide another repository carries
    serving this one;
  - **fix from a report** — `from report <path>`, or `from report`
    alone: the `## 8. Stack friction` section of that observation
    report (the latest one under `.odd/observe-run-reports/` whose
    `stack` is a custom one, when none is named — `odd-memory`'s
    report script reads it: `read <path> --sections 1,8`) is the work
    list, and nothing else; the stack is the report's `stack`, unless
    `for stack <name>` says otherwise. A report whose section 8 reads
    `none`, or a report on a built-in stack, is nothing to fix: say
    so and stop.
- **The name.** `<name>` is the directory's name, kebab-case, and the
  name decides. A name that is a `STACKS` value of the
  `observability-cli-guides` skill's `builtin-stacks.md` (or, when
  the request gives no name, a phrasing its "Also called" column
  maps) is refused: a stack the package ships changes through a
  package PR with live verification, never through a directory in the
  user's repository. A new name for a backend the package ships **is**
  a creation when the query surface differs (`curl` against the HTTP
  API of a backend the package queries through its CLI). A name whose
  directory exists is a completion whatever the verb; a name with no
  directory is a creation. A single-file stack an earlier contract
  wrote (`.odd/observability-stacks/<name>.md`) is not read: say so,
  and create the directory — the old file is the user's to delete in
  the same review.
- **The sources, in order** — the user's instructions (their word is
  the authority for what it covers), a URL they gave, a local path,
  then the web for the rest; the agent fetches and reads them, this
  prompt only lists them in the mission. A host that cannot fetch is
  stated here, so the agent fills from the user's sources alone and
  marks the rest unverified.
- **The backend must answer from this machine.** Live verification is
  the prerequisite of a stack, not a test suite: an invocation that
  cannot be run is never written as verified, and a backend the
  machine cannot reach stops a creation. Ask now, once, for what the
  agent will need to reach it — the instance's address, the name of
  the credential's variable, the CLI's configuration — by name, never
  a value; a caller that cannot answer sends the mission with those
  points listed as unverified, never invented.
- **A linked guide's amendment** (a completion or a fix on a stack
  whose guide is linked) ends in a pull request on the linked
  repository when the user can push to it: ask for that go here, once,
  before dispatching — the agent opens nothing without it, and
  displays the diff instead.

Never ask about anything the sources or the backend can answer — which
signals it carries, how its CLI paginates, what a query returns: that
is the agent's research, and the one list it comes back with when
nothing settled a point.

Then invoke the `stack-instrumentation-expert` agent. Build the
mission from the arguments and the answers above:

- `Skills: <directory>` — the `skills` line of the `package-layout`
  skill's `scripts/layout.py`, run once here and copied: the agent
  opens the skills' files there, by section, and never searches for
  them.
- Arguments: $ARGUMENTS
- Expected fields (any order): the **shape** (create, complete, link,
  fix from report), the **name**, the **sources** in the order above,
  the user's **instructions** verbatim, the **report path** and the
  friction bullets it carries for a fix, the **reachability** answers
  (what the agent can reach, by name), whether the host can **fetch**,
  and for a linked guide the **go for a pull request** (given,
  declined, or not asked).

One round-trip to expect: the agent stops before persisting when the
backend does not answer from this machine, or when a point neither the
sources nor the backend settled needs the user — it comes back with
one list, by name; put it to the user, and re-dispatch with the
answers. Never let the agent invent what the user did not say.

Close the mission with the `## Show` of `odd-memory`'s
`observability-stack` reference: render its synthesis of the stored
stack as the final answer, stating the stored path, and **offer the
switch** — `/odd-config switch to <name>` — which checks the stack
again and ends in the connection proof. The guide and the scripts —
not the synthesis — are what every run against the stack reads: never
re-dump them in the conversation.
