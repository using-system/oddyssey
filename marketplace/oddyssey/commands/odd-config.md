---
description: "Display the current oddyssey backend configuration - configured stack and environment, targeted instance, connection proof - then offer to change it: pick a backend from the full list, built-in or custom, and route the switch to the backend-configuration skill's Switch; targets a deployment environment; persists a stack's targeting values, per environment when one is named. A custom stack is written by /odd-instrument-stack, never here"
argument-hint: "switch to <stack> (local | grafana | datadog | dynatrace | azure-monitor | cloudwatch | a custom stack) [in <environment>] | target <environment> | clear the environment | persist <value> for <stack> [in <environment>] | clear <value> for <stack> [in <environment>]"
---

Answer "where do my missions point?" - and let the user change the
answer. The display is read-only: nothing is written until the user
picks a change.

- Arguments: $ARGUMENTS
- Expected fields (optional, free-form): a target backend
  (`switch to datadog`, `use the local stack`, `switch to seq` for a
  custom stack the repository carries), a deployment environment to
  target or clear (`target prod`, `clear the environment`), a targeting
  value to
  persist or clear (`persist workspace <guid>`,
  `clear the workspace for azure-monitor`) - in an environment when
  one is named (`switch to cloudwatch in prod`, `persist log group
  <name> for cloudwatch in prod`: the value lands in that environment's
  entry of the stack, `prod-cloudwatch`), an explicit local-port
  change (`set the local Grafana port to 3001`). A request to create,
  complete, link or fix a custom stack is `/odd-instrument-stack`'s
  (the last section says so). No arguments = display first.

When the arguments already name a target backend, an environment, or a
persist or clear
request, skip the display-first flow and route straight to the
`backend-configuration` skill's `## Switch` - it owns those entries: a named
backend runs the full switch (with the environment, when one is
named), `target <environment>` and `clear the environment` are its
switch step's `environment` write, a bare targeting value enters at its
`stack_config` step and stands alone, and a clear is the same step's
null write. The verification it ends with produces the display anyway,
so nothing is lost by skipping ahead. A request to create, complete,
link or fix a custom stack is answered by the last section, before
anything else.

An explicit local-port ask is neither of those - ports never belong in
`stack_config`. It is an `odd_config_set {"local": {...}}` write this
prompt performs itself, and only after stating what the user is
signing up for: changing a port while the stack container exists
resets it immediately, wiping ALL stored telemetry machine-wide (the
result embeds the reset outcome).

With no arguments, in this order:

1. **Display.** Run the `backend-configuration` skill's `## Check` for the
   configured stack: the stack and the configured environment (none
   when unset; on the local stack the environment is `local` by
   construction and the field inert), the effective configuration in
   that backend's own
   display shape (the `## Configuration display` section of its
   `observability-cli-guides` reference) - the entry the pair resolves
   to, named - which instance, tenant,
   or site the runs will hit, and the connection proof. Surface any
   `invalid_ignored` field `odd_config_get` reports - the stored value
   was tolerated but ignored, and only the user can say what they meant.
   Name the effect per field: a `local.*` port fell back to its default,
   a `stack_config` dotted name was simply dropped - nothing defaults it,
   so it now reads as not persisted; an `environment` value was dropped
   - the runs read the stack's plain entry until `target <environment>`
   sets it again; a `stack` value no longer accepted
   (a built-in the package removed, a custom stack whose declaration is
   gone) fell back to the default stack - say which stack the runs now
   hit, and offer the switch, or `/odd-instrument-stack create a stack
   <name>` to bring the backend back as a custom one.
2. **Offer the change**, starting with **"Change backend?"**: list the
   built-in stacks from the `observability-cli-guides` skill's
   `references/builtin-stacks.md` - every `STACKS` value with its
   one-line "where" (local or remote) - then the custom stacks the
   observed repository carries (`.odd/observability-stacks/*/guide.md`,
   one line each, marked `custom`), with the current one marked, and
   the line "or `/odd-instrument-stack create a stack <name>` for a
   backend not listed" - and, on a remote stack, "or `target
   <environment>` to read the values persisted for another
   environment". Anything the user
   picks goes to the `backend-configuration` skill's `## Switch`, which
   owns the switch end to end: CLI presence preflight with a guided
   install offer, the contract check for a custom stack, the persisted
   switch, the environment, the `stack_config` values per stack and per
   environment, and the re-verification
   through its `## Check`.

Displaying never writes configuration - not the stack, not the
environment, not a
`stack_config` value, not a port. A user who only wanted to look ends
this prompt with exactly the configuration they started with.

## A custom stack is written elsewhere

A backend the package does not ship becomes a custom stack — a
directory in the observed repository, `.odd/observability-stacks/<name>/`,
its `guide.md` carrying the same sections as a built-in reference and
its `scripts/` the query scripts the guide names — and this prompt
never writes one: creating, completing, linking or fixing a custom
stack is `/odd-instrument-stack`'s work, through the stack expert it
dispatches, with the live verification that authoring needs. A request
that asks for one here ("create a stack seq", "for stack seq: ...",
"linked to ...") is answered with that prompt's invocation and stops.
What this prompt does with a custom stack is list it (the display
above), switch to it (`## Switch`, the check first) and persist its
declared values — never author it.
