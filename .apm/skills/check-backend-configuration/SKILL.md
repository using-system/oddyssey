---
name: check-backend-configuration
description: Display, verify, and guide the observability CLI configuration for the configured stack backend before an observation or verify run. Use before dispatching an observe/verify mission, when the configured stack must be confirmed, when the backend CLI's connection must be proven, or when the user needs guidance to set their CLI up. Stack-agnostic - everything about a given stack comes from its observability-cli-guides reference. Never authenticates on the user's behalf - it verifies, displays, and guides.
---

# Check the Backend Configuration

The user configures their observability CLI themselves; agents never run
interactive auth (OAuth device codes and SSO browser logins stall
subagents — observed). What this skill does instead: resolve the
configured stack, show which instance the runs will hit, prove the CLI is
connected, and guide the user when it is not.

This skill knows no stack by name. Everything about a stack — its CLI,
what to display, how to prove the connection, what to say when it
fails — lives in that stack's reference file in the
`observability-cli-guides` skill, `references/<stack>.md`; the list of
stacks is that skill's `references/builtin-stacks.md`. This file is the
method; the reference is the content.

## 1. Resolve the stack

`odd_config_get` names the configured stack — one of the values
`builtin-stacks.md` lists. When the mission or the instructions name a
different one, they win — whether the switch persists is the
**caller's call**: `odd-observe` persists it with `odd_config_set` so
the next run starts from it; `odd-verify` states the divergence and
does not persist (the stored report is the contract it replays). Open
the stack's row in `builtin-stacks.md` and, from it, the stack's
reference file: the rest of this skill is that file's
`## Configuration display` section, applied in order.

A reference may say that another skill owns the whole method for its
stack (the default stack's does — the skill it names carries the CLI
context, the ports, and the datasource identifiers, and this skill only
routes to it). Follow that routing; the reference still says what to
display and what proves the connection.

## 2. Resolve the CLI and read its configuration

The reference's `## CLI binary` section names the binary, the
**Detect** command, and the **Install** steps (a reference may route
that section to another reference's — follow it).

**Prove the binary exists before reading anything**: run the Detect
command as written, in a shell **without `set -u`** (a Detect command
may reference an environment variable that is usually unset, and under
`-u` the check would abort instead of answering). A non-zero exit means
the binary is absent — an **installation** problem, never a
configuration one: say "the `<binary>` CLI is not installed" (naming
the reference's binary, never "CLI not configured"), route to the
`update-backend-configuration` skill's guided install offer, and resume
here once the user has installed; if they decline, stop with the same
clear error — the mission cannot query this backend until the binary
exists. Everything below — display, probe, guidance — assumes a binary
that runs.

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
not resolve to `update-backend-configuration` for correction, once;
the reference says what to do when the corrected value fails too.

## 3. Prove the connection

Run the reference's `### Connection proof` — its cheapest probe (whoami,
list datasources, or the equivalent), read the way the reference says
(some CLIs exit 0 whether authenticated or not; the reference names the
real signal). Any successful response = connected — evidence over
impressions. Failure = **stop with a clear error** naming the backend
and what is missing ("CLI not configured for <backend> — see its
observability-cli-guides reference") — never attempt to authenticate on
the user's behalf, and never invent, echo, or store credentials.

## 4. Guide what is missing

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
