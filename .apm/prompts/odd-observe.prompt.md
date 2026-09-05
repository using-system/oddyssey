---
description: Observe a running service through its telemetry (local stack or remote backend) and get the plan-ready observation report
---

Invoke the `observe-run` agent. It owns the whole method and the report
contract - this prompt only hands it a well-formed mission.

Preflight first - in the main conversation, before any dispatch (the
steps needing the user cannot happen inside a subagent):

1. Resolve the target stack: the configured one (`odd_config_get`), or
   the one the arguments name - a stack is one of the values the
   `observability-cli-guides` skill's `references/builtin-stacks.md`
   lists (its **Also called** column maps a user's phrasing onto one),
   **or a custom stack the observed repository carries**: a phrasing on
   no row is a custom stack's name when `.odd/observability-stacks/<name>.md`
   exists in the observed repository - `<name>` is the file's stem, the
   phrasing lowercased and kebab-cased ("my stack seq" is `seq`). A
   phrasing on neither is a deployment-environment expectation ("on
   prod"), never a switch - see below; when it reads as a stack's name
   rather than a location word, list that directory and ask before
   reading it as an environment (a misspelled custom name is not an
   environment). A named stack is persisted so the next run starts
   from it: a built-in one with `odd_config_set {"stack": "<name>"}`; a
   custom one the way the `backend-configuration` skill's `## Switch`
   step 3 writes it - the file checked first, the payload the check
   prints passed verbatim - never a bare name, which the server refuses
   for an undeclared stack. A local mission on a non-local stack
   switches to `local` - the local stack is self-serve, nothing to
   authenticate; every other **built-in** stack value names a remote
   backend (for `grafana`, the gcx context says which instance), and a
   custom stack is whatever its file targets.

2. Run the `backend-configuration` skill's `## Check`: show the CLI's effective
   configuration to the user (no confirmation needed), and stop where
   the skill stops, in its own words — the binary is **not installed**:
   it offers the guided install and resumes once the binary exists,
   stopping only if the user declines, and nothing is dispatched
   meanwhile; or the connection proof failed, **"CLI not configured
   for <backend>"**: it guides the setup and never authenticates on the
   user's behalf; never relabel the first as the second. Ask for
   whatever the mission still needs (instance URL, tenant, access
   material by name) before dispatching. Carry the skill's closing
   `Preflight:` handoff block into the mission block verbatim: the
   agent then reads the reference's other sections only (never the
   preflight's four: CLI binary, Setup, Configuration display, What to
   persist) and never re-proves what the preflight proved.
3. When the arguments name a stored benchmark, read its manifest under
   `.odd/benchmarks/<name>/` for the target service (the service the
   mission uses unless the arguments name one), and - unless the
   arguments say someone else is running it - ensure the `k6` binary
   is present, per the `k6-guides` skill's `install.md` auto-install
   step: `command -v k6`; when it is missing, run `brew install k6`
   directly when Homebrew is available (no confirmation - k6 needs no
   account and no configuration), otherwise follow that reference's
   non-interactive path for the platform or hand the remaining steps
   to the user and stop.
4. Resolve the **depth** — `quick` or `full`, how far the mission goes
   (the agent's Depth section) — from the arguments when they carry it,
   on the user's phrasing in any language, the way step 1 resolves a
   stack from the **Also called** column: "quick", "fast", "simple
   report", "just check that ...", "a first look" resolve to `quick`;
   "audit", "full sweep", "complete", "before the SDD wave" resolve to
   `full` — examples, not a closed list. A resolved depth is stated in
   the preflight's display and in the mission block, never asked again.
   Only when the arguments carry no depth signal, ask the user — with
   the host's structured-question tool when it has one (Claude Code:
   `AskUserQuestion`) — `quick` first and marked recommended, and carry
   the answer; when the service is missing too (the rule below), one
   ask carries both questions, never two in a row. A service-less
   discovery question (below) has no depth.

Build the mission block from the arguments below, applying the agent's own
defaults for every field not specified:

- `Skills: <directory>` - the parent directory of this package's
  installed skills: the base directory the host prints when one of
  them is invoked (`backend-configuration` in the preflight above),
  minus that skill's own directory name. The agent opens the skills'
  files there, by section, and never searches for them. Derived at run
  time, always carried, never guessed.
- Arguments: $ARGUMENTS
- Expected fields (any order, free-form): service name(s), stack
  (defaults to the configured one - the preflight resolved it), mode
  (drive / observe / post-hoc), depth (quick / full - the preflight
  resolved or asked it), benchmark, window, focus, baseline
  expectations.
- `benchmark` names a stored k6 benchmark - its directory name under
  `.odd/benchmarks/` or that path. `run .odd/benchmarks/<name>/` means
  mode `drive` with that benchmark; "someone is running <name>" means
  mode `observe` with it. It composes with `drive` and `observe`, never
  with `post-hoc` (the agent refuses that combination). The service is
  the manifest's target service (read in the preflight) unless the
  arguments name one.
- The deployment environment is not a mission field: the agent detects
  it from the telemetry (`deployment.environment.name`) and records it -
  never pass one, never guess one here. When the arguments name one
  ("on prod", "on uat"), it is neither the stack nor a mission input:
  carry it into the baseline expectations, so the agent compares it
  against the environment it detects and flags a divergence.
- If no service name can be determined - no argument names one and no
  benchmark manifest supplies one - and the ask is an observation
  mission, ask for it before invoking the agent. A service-less
  **discovery question** about the stack's telemetry (which services
  exist, what emits metrics, over what window) is answered directly in
  the main conversation instead - after the preflight, with the
  backend's query quoted as evidence, no dispatch and no report -
  offering the full mission as the follow-up.

Close the mission with the `## Show` of `odd-memory`'s
`observe-run-report` reference: render its
synthesis from the persistence return value the agent's reply carries
(stored path, carrying commit, the synthesis block) as the final
answer, stating the stored path — no re-read of the file just
written. The report file - not the synthesis - is the deliverable the
next spec-driven wave consumes: never re-dump the raw report in the
conversation, and never let the synthesis replace the stored file as
the plan's input.
