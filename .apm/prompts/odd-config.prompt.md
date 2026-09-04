---
description: "Display the current oddyssey backend configuration - configured stack, targeted instance, connection proof - then offer to change it: pick a backend from the full list, built-in or custom, and route the switch to the backend-configuration skill's Switch. Also creates or completes a custom stack file for a backend the package does not ship - from the documentation the user points at, their instructions, or web research - checked against the reference contract and persisted through odd-memory"
---

Answer "where do my missions point?" - and let the user change the
answer. The display is read-only: nothing is written until the user
picks a change.

- Arguments: $ARGUMENTS
- Expected fields (optional, free-form): a target backend
  (`switch to datadog`, `use the local stack`, `switch to seq` for a
  custom stack the repository carries), a targeting value to
  persist or clear (`persist workspace <guid>`,
  `clear the workspace for azure-monitor`), an explicit local-port
  change (`set the local Grafana port to 3001`), or a **custom stack
  to create or complete** (`create a stack seq`, with optional
  sources - a documentation URL, a local path to documentation, free
  instructions - and `for stack seq: <instructions>` to complete an
  existing file). No arguments = display first.

When the arguments already name a target backend or a persist or clear
request, skip the display-first flow and route straight to the
`backend-configuration` skill's `## Switch` - it owns those entries: a named
backend runs the full switch, a bare targeting value enters at its
`stack_config` step and stands alone, and a clear is the same step's
null write. The verification it ends with produces the display anyway,
so nothing is lost by skipping ahead. A create or complete request
goes to the section of its own below, before anything else.

An explicit local-port ask is neither of those - ports never belong in
`stack_config`. It is an `odd_config_set {"local": {...}}` write this
prompt performs itself, and only after stating what the user is
signing up for: changing a port while the stack container exists
resets it immediately, wiping ALL stored telemetry machine-wide (the
result embeds the reset outcome).

With no arguments, in this order:

1. **Display.** Run the `backend-configuration` skill's `## Check` for the
   configured stack: the effective configuration in that backend's own
   display shape (the `## Configuration display` section of its
   `observability-cli-guides` reference), which instance, tenant,
   or site the runs will hit, and the connection proof. Surface any
   `invalid_ignored` field `odd_config_get` reports - the stored value
   was tolerated but ignored, and only the user can say what they meant.
   Name the effect per field: a `local.*` port fell back to its default,
   a `stack_config` dotted name was simply dropped - nothing defaults it,
   so it now reads as not persisted.
2. **Offer the change**, starting with **"Change backend?"**: list the
   built-in stacks from the `observability-cli-guides` skill's
   `references/builtin-stacks.md` - every `STACKS` value with its
   one-line "where" (local or remote) - then the custom stacks the
   observed repository carries (`.odd/observability-stacks/*.md`, one
   line each, marked `custom`), with the current one marked, and the
   line "or create a stack for a backend not listed". Anything the user
   picks goes to the `backend-configuration` skill's `## Switch`, which
   owns the switch end to end: CLI presence preflight with a guided
   install offer, the contract check for a custom stack, the persisted
   switch, the per-stack `stack_config` values, and the re-verification
   through its `## Check`.

Displaying never writes configuration - not the stack, not a
`stack_config` value, not a port. A user who only wanted to look ends
this prompt with exactly the configuration they started with.

## Creating or completing a custom stack

A backend the package does not ship becomes one file in the observed
repository, `.odd/observability-stacks/<name>.md`, with the same
sections as a built-in reference: the `observability-cli-guides`
skill's `references/CONTRACT.md` says what it carries, the `odd-memory`
skill's `observability-stack` reference how it lives - read both,
by section, before writing anything. This prompt writes the file; the
switch (`backend-configuration`'s `## Switch`) checks and uses it.

**Resolve first.** `<name>` is the file's stem, kebab-case, and the
name decides. A name that is a `STACKS` value of `builtin-stacks.md`
(or, when the request gives no name, a phrasing its "Also called"
column maps) is not a creation: say so and route to `## Switch` - a
stack the package ships changes through a package PR with live
verification, never through a file in the user's repository, and the
same refusal answers a `for stack <built-in>: ...` request. A new
name for a backend the package ships **is** a creation when the query
surface differs (`curl` against the HTTP API of a Grafana the package
queries with gcx): the file is about that surface. A name whose file
already exists is a **completion**, whatever the verb used; a name
with no file is a **creation**. Creating or completing is the user
picking a change: the file is written, and committed as the memory
contract says - on its work branch, which the persistence creates
when the repository sits on its default branch.

**Sources, in this order** - what the user gave first, the web for the
rest:

- **instructions** in the request (an endpoint, a CLI, a flag, a
  property name, "no authentication"): the user's word is the
  authority for what it covers, over the documentation and the web
  when they disagree - written in as told, attributed to the user
  with the date, the disagreement noted next to it;
- a **URL** the user gave: fetch it, and the few pages it links that
  answer the query surface, the authentication and the signals - not
  the whole site; a moved page is followed to where it resolves;
- a **local path**: read the documentation under it;
- the **web**, official documentation first, for everything the
  sources above did not settle. A host that cannot fetch fills the
  file from the user's sources alone, marks every point they left open
  as unverified with the date, and lists them in the reply - never
  from memory.

Every command in the file **links to the page it comes from** (the
contract's rule) - the page that answered, at the address it resolved
to; a user's instruction links to nothing and says so. The backend's
own signal list wins over the user's: a signal the user did not name
is still documented (marked as outside the instruction), a signal the
backend cannot serve says so.

**Create.** Scaffold the file from the contract's fenced heading
block - every mandatory `##` and `###` heading, in the block's order;
the block is the list, this prompt only says what fills each - with
the frontmatter on top
(`stack: <name>`, `stack_config_fields: []` until the sections below
say what the switch must persist). Then fill each section from the
sources: the query surface (a dedicated CLI, an HTTP API through
`curl`, anything the backend answers to - a CLI is one option, never a
requirement), how that surface authenticates and targets an instance
(a credential is an environment variable **name** or the CLI's own
configuration, never a field, never a value; a real endpoint or
identifier is a `stack_config` field the file names), how to query
each signal the backend carries (metrics, logs, traces, profiles - a
signal it cannot serve says so, one it documents but the file could
not exercise is marked unverified with the date), how to read the
output, whether the surface is safe to run concurrently, the planning
notes, the display and the connection proof (the one cheapest call
and the real signal of success - an exit code is not always one), the
change-request phrasings, what to persist. Declare in the frontmatter
exactly the fields `## What to persist` names - nothing when the
surface carries its own context, like a CLI with a configured
connection; a field when the surface takes the instance per call,
like `curl` (a `localhost` default may be written in the file as an
example, it is not a real endpoint; a real instance's address is the
field's value, persisted, never written in the file).

**Verify while filling** when the backend answers from this machine:
run each command as it lands, keep what answered and note the output
shape; a command that could not be run is marked unverified with the
date - never upgraded without a measurement. A backend the machine
cannot reach leaves the whole file unverified, and the switch's
connection proof is then its first measurement.

**Complete.** `for stack <name>: <instructions>` (or a create request
naming an existing file) changes the sections the instructions
touch, and only those: read the stored file by section, apply the
instruction or the new source, and present the change as a **diff
against the stored file** before persisting it - living source,
reviewed, never silently rewritten. An instruction never upgrades an
unverified note to verified: only a run does.

**Ask once.** What neither the sources nor the web settled - the
instance's address, which signals the backend really carries, the
name of the credential - comes back as **one list**, by name, never a
value, and the file waits for the answers. When nobody can answer
(a caller that cannot ask), the file proceeds with those points
marked unverified, and the reply carries the list; what the user does
not know is written as unverified, not invented.

**Check, then persist.** Run the check `## Switch` runs
(`python3 <the observability-cli-guides skill's directory>/scripts/check_stack_reference.py --declaration .odd/observability-stacks/<name>.md`)
on the draft and fix what it lists before anything is committed.
Persist through the `odd-memory` stack reference - its branch, its
lone commit, its `## Show` as the reply's synthesis, never the file
body - then **offer the switch**: `backend-configuration`'s
`## Switch` runs the check again, persists the declaration (with the
declared values in the same call when they are known) and ends in the
connection proof and the preflight handoff - the handoff carries the
targeting values the synthesis does not, by design. A user who
declines keeps the file and nothing else changes.
