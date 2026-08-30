---
name: check-backend-configuration
description: Display, verify, and guide the observability CLI configuration for the configured stack backend before an observation or verify run. Use before dispatching an observe/verify mission, when the configured stack must be confirmed, when the backend CLI's connection must be proven, or when the user needs guidance to set their CLI up. Never authenticates on the user's behalf - it verifies, displays, and guides.
---

# Check the Backend Configuration

The user configures their observability CLI themselves; agents never run
interactive auth (OAuth device codes and SSO browser logins stall
subagents — observed). What this skill does instead: resolve the
configured stack, show which instance the runs will hit, prove the CLI is
connected, and guide the user when it is not.

## 1. Resolve the stack

`odd_config_get` names the configured stack (`local` — the default —,
`grafana`, `azure-monitor`, `cloudwatch`, `datadog`, `dynatrace`,
`splunk`). When the mission or the instructions name a different one,
they win — whether the switch persists is the **caller's call**:
`odd-observe` persists it with `odd_config_set` so the next run starts
from it; `odd-verify` states the divergence and does not persist (the
stored report is the contract it replays). `local` routes straight to
the local stack — steps 2-4 are **replaced by** the Local specificity
section below.

## 2. Resolve the CLI and read its configuration

Open the stack's reference in the `observability-cli-guides` skill — it
names the CLI (gcx, Pup, dtctl, az, aws, splunk) and the commands that
display its current configuration/context.

**Prove the binary exists before reading anything**: run the
reference's `## CLI binary` **Detect** command as written, in a shell
**without `set -u`** (splunk's Detect references `$SPLUNK_HOME`,
usually unset). A non-zero exit means the binary is absent — an
**installation** problem, never a configuration one: say "the
`<binary>` CLI is not installed" (naming the reference's binary, never
"CLI not configured"), route to the `update-backend-configuration`
skill's guided install offer, and resume here once the user has
installed; if they decline, stop with the same clear error — the
mission cannot query this backend until the binary exists. Everything
below — display, probe, guidance — assumes a binary that runs.

Then open this skill's own reference for the stack
(`references/<stack>.md`) — it says exactly what
to display for that backend and where each value comes from, including
the persisted `stack_config` values from `odd_config_get`. Show that
configuration to the user **as-is, no confirmation needed** — it is
informative: which instance, tenant, or site the queries are about to
hit is exactly what a user wants to see before a run, and what catches a
wrong-target mistake before it costs a mission. Every display ends with
the reference's change-request phrasing example, so the user knows how
to ask for a change.

## 3. Prove the connection

Run the reference's cheapest probe (whoami, list datasources, or the
equivalent). Any successful response = connected — evidence over
impressions. Failure = **stop with a clear error** naming the backend and
what is missing ("CLI not configured for <backend> — see its
observability-cli-guides reference") — never attempt to authenticate on
the user's behalf, and never invent, echo, or store credentials.

## 4. Guide what is missing

Point the user at the exact setup steps in the backend's reference, ask
for the inputs the mission needs (instance URL, tenant, workspace, where
the credentials come from — by name, never values), and re-run the probe
once the user says the setup is done. The probe's success is the exit
criterion, not the user's assurance. One check before guiding remote
auth: on `grafana` with no remote gcx context configured, offer the
alternative first — if the user meant the local stack, the fix is
`odd_config_set {"stack": "local"}`, not an authentication.

## Local specificity

`stack: local` is the local stack: apply the `setup-local-stack` skill
(isolated gcx context, datasource UIDs, ports from the global
configuration) — that skill owns the local method, this one only routes
to it, and it is fully self-serve: no user authentication to guide, so a
missing gcx setup on a fresh machine is NOT a "CLI not configured"
error. The connection proof is then `gcx config check` against the
isolated local context. The display shape is
[`references/local.md`](references/local.md) — Grafana URL and both OTLP
endpoints resolved from `odd_config_get`, never hardcoded — while
`setup-local-stack` keeps owning the method. `grafana` always means a
**remote** Grafana — the gcx context says which instance.
