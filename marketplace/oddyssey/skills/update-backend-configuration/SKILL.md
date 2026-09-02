---
name: update-backend-configuration
description: "Own the backend switch of the global oddyssey configuration: verify the target backend's CLI is installed (offer a guided install when missing), persist the switch via odd_config_set, persist the per-stack stack_config values the missions will need, and hand back to check-backend-configuration for the connection proof. Stack-agnostic - the stack list and everything about a given stack come from the observability-cli-guides skill. Use when the user asks to change the configured stack/backend or to persist backend targeting values. Never installs silently, never authenticates on the user's behalf, never stores secrets."
---

# Update the Backend Configuration

Switching backends is a write, and a write deserves a preflight: a stack
persisted for a CLI that is not on the machine turns every later mission
into the same discovery. So this skill checks the binary first, writes
second, and proves nothing itself — the proof is
`check-backend-configuration`'s job, and step 5 hands it over.

Three lines this skill never crosses: it never installs anything
silently (it offers, the user runs or approves), it never authenticates
on the user's behalf, and it never stores a secret — credentials stay in
the CLI's own auth store and are referred to by name only.

This skill knows no stack by name. The valid stacks, their aliases,
their CLIs, and what each persists come from the
`observability-cli-guides` skill: `references/builtin-stacks.md` for
the list, `references/<stack>.md` for the stack — its `## CLI binary`
section for the preflight, its `## What to persist` section for the
`stack_config` write.

## 1. Resolve the target stack

The target is one of the `STACKS` values `builtin-stacks.md` lists —
`odd_config_set` accepts nothing else. Map the user's phrasing onto a
row through that table's **Also called** column — a vendor name, a
product name, or the words for the stack on this machine each name
exactly one value there.

Anything that does not resolve is an **error naming the valid list**
(the table's first column), not a guess and not a passthrough:
`odd_config_set` would reject it anyway, and a spelled-out list is what
lets the user correct it in one turn.

## 2. CLI presence preflight

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

## 3. Persist the switch

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
desired env is the way to reapply those. Port changes stay the **caller's explicit
ask**: this skill never changes ports on its own, and it never bundles a
port change into a backend switch the user did not request.

## 4. Persist the stack_config

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
another) — enters the skill here and stands alone. Resolve the target
stack (section 1) for validation only, so the values land in the right
entry and are read against the right reference; **skip the switch
persist** (section 3) entirely; write the values as above; end at
verification (section 5) as every path does. The configured stack is
left exactly as it was — naming a backend to persist values for is not
asking to point the missions at it, and a `{"stack": ...}` write here
would be an unrequested switch.

## 5. Verify

Run `check-backend-configuration` against the new stack — or against
the configured one, untouched, on a persist-only pass. Its display plus
its connection proof is this skill's **exit criterion** — a switch is
done when the CLI answers for the new backend, not when the write
returns. Failures come back as that skill's guidance (setup steps, the
inputs it needs by name); this skill does not authenticate and does not
retry the auth on the user's behalf.

Two outcomes worth stating explicitly rather than swallowing: the
configuration is switched but the CLI is unconfigured (the write stands,
the guidance is the next step), and the user meant the default stack
all along (the fix is `odd_config_set {"stack": "<default>"}`, the row
`builtin-stacks.md` marks as the default, not an authentication).
