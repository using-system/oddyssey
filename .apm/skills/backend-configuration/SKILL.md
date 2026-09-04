---
name: backend-configuration
description: "Own the configured observability backend, in two sections invoked by name. Check: display the configured stack and the instance the runs will hit, prove the CLI connected, guide the user when it is not, and hand the preflight over to the mission. Switch: verify the target backend's CLI is installed (offer a guided install when missing), persist the switch via odd_config_set, persist the per-stack stack_config values the missions will need, then run Check for the proof. Stack-agnostic - the stack list and everything about a given stack come from the observability-cli-guides skill. Use before dispatching an observe, verify or bench mission, when the configured stack must be confirmed or the CLI's connection proven, when the user needs guidance to set their CLI up, and when the user asks to change the configured backend or to persist targeting values. Never installs silently, never authenticates on the user's behalf, never stores or echoes a secret."
---

# The Backend Configuration

The user configures their observability CLI themselves; agents never run
interactive auth (OAuth device codes and SSO browser logins stall
subagents — observed). This skill resolves the configured stack, shows
which instance the runs will hit, proves the CLI is connected, and
guides the user when it is not (`## Check`); and it owns the write —
the switch to another backend and the targeting values persisted for
it (`## Switch`). A switch is a write, and a write deserves a preflight:
a stack persisted for a CLI that is not on the machine turns every
later mission into the same discovery, so the switch checks the binary
first, writes second, and ends in `## Check`'s proof.

Three lines this skill never crosses: it never installs anything
silently (it offers, the user runs or approves), it never authenticates
on the user's behalf, and it never stores or echoes a secret —
credentials stay in the CLI's own auth store and are referred to by
name only.

This skill knows no stack by name. Everything about a stack — its CLI,
what to display, how to prove the connection, what to say when it
fails, what to persist — lives in that stack's reference file in the
`observability-cli-guides` skill, `references/<stack>.md`; the list of
stacks, their aliases and their CLIs is that skill's
`references/builtin-stacks.md`. This file is the method; the reference
is the content.

**Read by section, never the whole file.** A reference runs a few
hundred lines, and this skill needs the four sections the reference
contract reserves for it: `## CLI binary` (Detect and Install),
`## Configuration display` (what to show, the connection proof, the
change-request phrasings), `## What to persist` (the `stack_config`
write), and `## Setup` only when there is something to guide. When a
section routes to another file or skill ("read that section", "the
method is X's"), read the routed **section**, never the file around it.
Every other section of the reference — the query surface, output
reading, targeting and planning notes — is the agent's, read once, by
the agent, after dispatch — never here.

A reference may say that another skill owns the whole method for its
stack (the default stack's does — the skill it names carries the CLI
context, the ports, and the datasource identifiers, and this skill only
routes to it). Follow that routing to the section the reference names;
the reference still says what to display and what proves the
connection.

## Check

### 1. Resolve the stack

`odd_config_get` names the configured stack — one of the values
`builtin-stacks.md` lists. When the mission or the instructions name a
different one, they win — whether the switch persists is the
**caller's call**: `odd-observe` persists it with `odd_config_set` so
the next run starts from it; `odd-verify` states the divergence and
does not persist (the stored report is the contract it replays). Open
the stack's row in `builtin-stacks.md` and, from it, the stack's
reference file: the rest of this section is that file's
`## Configuration display`, applied in order.

### 2. Resolve the CLI and read its configuration

The reference's `## CLI binary` section names the binary, the
**Detect** command, and the **Install** steps (a reference may route
that section to another reference's — read that section there, and
only it).

**Prove the binary exists before reading anything**: run the Detect
command as written, in a shell **without `set -u`** (a Detect command
may reference an environment variable that is usually unset, and under
`-u` the check would abort instead of answering). A non-zero exit means
the binary is absent — an **installation** problem, never a
configuration one: say "the `<binary>` CLI is not installed" (naming
the reference's binary, never "CLI not configured"), make `## Switch`'s
guided install offer (its step 2), and resume here once the user has
installed; if they decline, stop with the same clear error — the
mission cannot query this backend until the binary exists. Everything
below — display, probe, guidance — assumes a binary that runs.

Then follow the reference's `### Display` — it says exactly what to
display for that backend and where each value comes from, including
the persisted `stack_config` values from `odd_config_get`. Show that
configuration to the user **as-is, no confirmation needed** — it is
informative: which instance, tenant, or site the queries are about to
hit is exactly what a user wants to see before a run, and what catches a
wrong-target mistake before it costs a mission. Every display ends with
the reference's `### Change-request phrasing` examples, so the user
knows how to ask for a change.

Where a reference defines a **targeting proof** — a persisted
`stack_config` value that must resolve against the backend before it
is trusted — run it as the reference says, and route a value that does
not resolve to `## Switch`'s persist-only path (its step 4) for
correction, once; the reference says what to do when the corrected
value fails too.

### 3. Prove the connection

Run the reference's `### Connection proof` — its cheapest probe (whoami,
list datasources, or the equivalent), read the way the reference says
(some CLIs exit 0 whether authenticated or not; the reference names the
real signal). Any successful response = connected — evidence over
impressions. Failure = **stop with a clear error** naming the backend
and what is missing ("CLI not configured for <backend> — see its
observability-cli-guides reference") — never attempt to authenticate on
the user's behalf, and never invent, echo, or store credentials.

### 4. Guide what is missing

Point the user at the exact setup steps in the reference's `## Setup`
section, ask for the inputs the mission needs (instance URL, tenant,
workspace, where the credentials come from — by name, never values),
and re-run the probe once the user says the setup is done. The probe's
success is the exit criterion, not the user's assurance. When the
reference names an alternative to offer **before** guiding
authentication (a remote stack whose CLI has no context configured may
mean the user wanted the default stack, and the fix is then
`odd_config_set {"stack": "<default>"}` — the row `builtin-stacks.md`
marks as the default — not a login), offer it first.

### 5. Hand off what you resolved

Close with a **preflight handoff** block — emitted only once step 3's
proof has succeeded; a block with a failed or absent `Proof:` line
never exists. The caller copies it into the mission block verbatim,
so the agent never re-reads the sections this skill just read nor
re-proves the connection — it reads the reference's other sections
only:

```text
Preflight: stack=<stack>, backend=<backend, or local>
Reference: <repo-relative path of the reference file>; read: CLI binary, Configuration display
CLI: <binary> <version>; context: <the isolated context's path, or the named context>
Target: <the Display's values on one line - URLs, ports, tenant/workspace/site names; never a credential>
Proof: <the probe command> -> <the real signal it returned>, at <UTC>
```

The `Target:` line carries what the Display showed — the real
targeting values the agent's queries need — and nothing more: never a
credential. The block is **conversation-scope**: a real tenant,
workspace, subscription or site name, a GUID, a login, a path under a
home directory all identify a real environment, and the agent's report
is a committed file — section 1 restates the stack and backend, never
this block, and any identifier a report must mention goes in as an
obviously fake placeholder (AGENTS.md's no-secrets rule, which covers
identifiers, not only credentials).

## Switch

### 1. Resolve the target stack

The target is one of the `STACKS` values `builtin-stacks.md` lists —
`odd_config_set` accepts nothing else. Map the user's phrasing onto a
row through that table's **Also called** column — a vendor name, a
product name, or the words for the stack on this machine each name
exactly one value there.

Anything that does not resolve is an **error naming the valid list**
(the table's first column), not a guess and not a passthrough:
`odd_config_set` would reject it anyway, and a spelled-out list is what
lets the user correct it in one turn.

### 2. CLI presence preflight

Open the target's reference and read its `## CLI binary` section — it
names the binary, the **Detect** command, and the **Install** steps. A
reference may route that section to another reference's when the same
binary queries both stacks; follow it.

Run the Detect command as written, in a shell **without `set -u`** — a
Detect command may reference an environment variable that is usually
unset, and under `-u` the check would abort instead of answering. A
non-zero exit is the **answer, not a failure**: it means "not
installed", and the preflight continues into the offer below.

When the binary is missing, **offer** the reference's Install steps:
name the binary, show the install command(s), and ask the user to run
one or to approve running it. Never install silently, never pick a
method for a user who has not answered. Pick one method only where the
reference lists several — two installs leave two binaries on `PATH`.
The offer is not a stop sign: if the user declines, say plainly that the
switch will persist but the missions will fail at the CLI until the
binary exists, and let them decide.

A reference may say its stack is fully self-serve — no account, no
authentication behind it (the default stack's does): a missing binary
there is the mildest case of all, a step to run, never a "CLI not
configured" error.

### 3. Persist the switch

Write it: `odd_config_set {"stack": "<target>"}`. The result carries the
effective configuration under `config` — report the new `stack` from
there, not from the request, so what is displayed is what was stored.

The switch alone touches nothing else: it does not boot, reset, or stop
the local stack container. A `stack_reset` block appears in the result
**only** when the same call also changed a local host port, because a
port change resets the stack immediately (wiping all stored telemetry,
`services_wiped` in the reset outcome) and carries the old container's
user-set environment forward best-effort — `env_preserved` lists the
carried variable **names**, never values. An empty `env_preserved`
means the live read failed; the recreation still reapplies whatever
`stack_config.local` persists, so only never-persisted variables
(credential-named ones) are gone — a bare `odd_stack_reset` with the
desired env is the way to reapply those. Port changes stay the
**caller's explicit ask**: this skill never changes ports on its own,
and it never bundles a port change into a backend switch the user did
not request.

### 4. Persist the stack_config

Follow the reference's `## What to persist` section. It says what
`stack_config` holds for that backend, where each value comes from, and
what to ask the user for — including the backends where the answer is
**nothing**, so the skill knows not to ask.

Write with `odd_config_set {"stack_config": {"<stack>": {...}}}`. The
payload is merged into that stack's entry and every other stack's entry
is left untouched, so a one-value correction is a one-value call. Values
are flat scalars (string, number, boolean) and nothing else: identifiers,
names, regions, GUIDs, group names. **Never a secret** — no password, no
API key, no token, no connection string carrying one. When the mission
needs a credential, the reference says which named credential the CLI's
own auth store must hold, and the name is all that is ever written down.
A `stack_config` write never boots or resets the stack container.

**Clearing a value** is the same write with `null`:
`odd_config_set {"stack_config": {"<stack>": {"<key>": null}}}` deletes
that key (deleting the last one leaves the present-but-empty entry —
"not configured", the normal state), and
`{"stack_config": {"<stack>": null}}` removes the stack's entry
entirely. A deletion never boots or resets the container either, and it
is the tool-surface answer to "clear the <value> for <stack>" — never
hand-edit the file.

An entry that is present and empty (`{"<stack>": {}}`) means "not
configured", which for the backends whose reference says `stack_config`
holds **nothing** — the context-bearing CLIs, whose own context names
the instance — is the **correct final state**: normal, not an error,
and not something to fill in with invented values.

A **persist-only** request — targeting values named, no switch asked
("persist workspace `<guid>` for <stack>" while the configured stack is
another) — enters the switch here and stands alone. Resolve the target
stack (step 1) for validation only, so the values land in the right
entry and are read against the right reference; **skip the switch
persist** (step 3) entirely; write the values as above; end at
verification (step 5) as every path does. The configured stack is
left exactly as it was — naming a backend to persist values for is not
asking to point the missions at it, and a `{"stack": ...}` write here
would be an unrequested switch.

### 5. Verify

Run `## Check` against the new stack — or against the configured one,
untouched, on a persist-only pass. Its display plus its connection
proof is the switch's **exit criterion** — a switch is done when the
CLI answers for the new backend, not when the write returns. Failures
come back as `## Check`'s guidance (setup steps, the inputs it needs by
name); the switch does not authenticate and does not retry the auth on
the user's behalf.

Two outcomes worth stating explicitly rather than swallowing: the
configuration is switched but the CLI is unconfigured (the write stands,
the guidance is the next step), and the user meant the default stack
all along (the fix is `odd_config_set {"stack": "<default>"}`, the row
`builtin-stacks.md` marks as the default, not an authentication).
