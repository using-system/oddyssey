---
description: "Display the current oddyssey backend configuration - configured stack, targeted instance, connection proof - then offer to change it: pick a backend from the full list and route the switch to the update-backend-configuration skill"
---

Answer "where do my missions point?" - and let the user change the
answer. The display is read-only: nothing is written until the user
picks a change.

- Arguments: $ARGUMENTS
- Expected fields (optional, free-form): a target backend
  (`switch to datadog`, `use the local stack`) or a targeting value to
  persist (`persist workspace <guid>`). No arguments = display first.

When the arguments already name a target backend or a persist request,
skip the display-first flow and route straight to the
`update-backend-configuration` skill - it owns both entries: a named
backend runs the full switch, a bare targeting value enters at its
`stack_config` step and stands alone. The verification it ends with
produces the display anyway, so nothing is lost by skipping ahead.

With no arguments, in this order:

1. **Display.** Run the `check-backend-configuration` skill for the
   configured stack: the effective configuration in that backend's own
   display shape (its `references/<stack>.md`), which instance, tenant,
   or site the runs will hit, and the connection proof. Surface any
   `invalid_ignored` field `odd_config_get` reports - the stored value
   was tolerated but ignored, and only the user can say what they meant.
   Name the effect per field: a `local.*` port fell back to its default,
   a `stack_config` dotted name was simply dropped - nothing defaults it,
   so it now reads as not persisted.
2. **Offer the change**, starting with **"Change backend?"**: list the
   seven backends - `local` (the local stack), `grafana` (a **remote**
   Grafana), `azure-monitor`, `cloudwatch`, `datadog`, `dynatrace`,
   `splunk` - with the current one marked. Anything the user picks goes
   to the `update-backend-configuration` skill, which owns the switch
   end to end: CLI presence preflight with a guided install offer, the
   persisted switch, the per-stack `stack_config` values, and the
   re-verification through `check-backend-configuration`.

Displaying never writes configuration - not the stack, not a
`stack_config` value, not a port. A user who only wanted to look ends
this prompt with exactly the configuration they started with.
