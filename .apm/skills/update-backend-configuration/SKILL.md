---
name: update-backend-configuration
description: "Own the backend switch of the global oddyssey configuration: verify the target backend's CLI is installed (offer a guided install when missing), persist the switch via odd_config_set, persist the per-stack stack_config values the missions will need, and hand back to check-backend-configuration for the connection proof. Use when the user asks to change the configured stack/backend or to persist backend targeting values. Never installs silently, never authenticates on the user's behalf, never stores secrets."
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

## 1. Resolve the target stack

The target is one of the seven `STACKS` values: `local` (the local
stack — the default), `grafana` (a **remote** Grafana), `azure-monitor`,
`cloudwatch`, `datadog`, `dynatrace`, `splunk`. Map the user's phrasing
onto one of them — "AWS" is `cloudwatch`, "Azure" is `azure-monitor`,
"my own Grafana" is `grafana`, "the local stack" is `local`.

Anything that does not resolve is an **error naming the valid list**,
not a guess and not a passthrough: `odd_config_set` would reject it
anyway, and a spelled-out list is what lets the user correct it in one
turn.

## 2. CLI presence preflight

Open the target's reference in the `observability-cli-guides` skill and
read its `## CLI binary` section — it names the binary, the **Detect**
command, and the **Install** steps. `local` uses that skill's
`grafana.md`: gcx is the local stack's mandatory query CLI, so a switch
to `local` needs the same binary a remote Grafana does.

Run the Detect command as written, in a shell **without `set -u`** —
splunk's Detect references `$SPLUNK_HOME`, which is usually unset, and
under `-u` the check would abort instead of answering. A non-zero exit
is the **answer, not a failure**: it means "not installed", and the
preflight continues into the offer below.

When the binary is missing, **offer** the reference's Install steps:
name the binary, show the install command(s), and ask the user to run
one or to approve running it. Never install silently, never pick a
method for a user who has not answered. Pick one method only where the
reference lists several — two installs leave two binaries on `PATH`.
The offer is not a stop sign: if the user declines, say plainly that the
switch will persist but the missions will fail at the CLI until the
binary exists, and let them decide.

A missing gcx on `local` is the mildest case of all — the local stack is
fully self-serve, there is no account and no authentication behind it,
so installing gcx is a step to run, never a "CLI not configured" error.

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
carried variable **names**, never values, and an empty `env_preserved`
means nothing was carried and a bare `odd_stack_reset` with the desired
env is the way to reapply it. Port changes stay the **caller's explicit
ask**: this skill never changes ports on its own, and it never bundles a
port change into a backend switch the user did not request.

## 4. Persist the stack_config

Open this skill's `references/<stack>.md`. It says what `stack_config`
holds for that backend, where each value comes from, and what to ask the
user for — including the backends where the answer is **nothing**, so
the skill knows not to ask.

Write with `odd_config_set {"stack_config": {"<stack>": {...}}}`. The
payload is merged into that stack's entry and every other stack's entry
is left untouched, so a one-value correction is a one-value call. Values
are flat scalars (string, number, boolean) and nothing else: identifiers,
names, regions, GUIDs, group names. **Never a secret** — no password, no
API key, no token, no connection string carrying one. When the mission
needs a credential, the reference says which named credential the CLI's
own auth store must hold, and the name is all that is ever written down.
A `stack_config` write never boots or resets the stack container.

An entry that is present and empty (`{"grafana": {}}`) means "not
configured", which for the context-bearing backends — `grafana`,
`datadog`, `dynatrace`, `splunk` — is the **correct final state**:
normal, not an error, and not something to fill in with invented
values.

## 5. Verify

Run `check-backend-configuration` against the new stack. Its display
plus its connection proof is this skill's **exit criterion** — a switch
is done when the CLI answers for the new backend, not when the write
returns. Failures come back as that skill's guidance (setup steps, the
inputs it needs by name); this skill does not authenticate and does not
retry the auth on the user's behalf.

Two outcomes worth stating explicitly rather than swallowing: the
configuration is switched but the CLI is unconfigured (the write stands,
the guidance is the next step), and the user meant the local stack all
along (the fix is `odd_config_set {"stack": "local"}`, not an
authentication).
