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

`odd_config_get` names the configured stack (`grafana`, `azure-monitor`,
`cloudwatch`, `datadog`, `dynatrace`, `splunk`). When the mission or the
instructions name a different one, they win — whether the switch persists
is the **caller's call**: `odd-observe` persists it with `odd_config_set`
so the next run starts from it; `odd-verify` states the divergence and
does not persist (the stored report is the contract it replays).
`grafana` may route to the local stack — see Local specificity below
before treating a missing gcx setup as an error.

## 2. Resolve the CLI and read its configuration

Open the stack's reference in the `observability-cli-guides` skill — it
names the CLI (gcx, Pup, dtctl, az, aws, splunk) and the commands that
display its current configuration/context. Show that configuration to the
user **as-is, no confirmation needed** — it is informative: which
instance, tenant, or site the queries are about to hit is exactly what a
user wants to see before a run, and what catches a wrong-target mistake
before it costs a mission.

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
criterion, not the user's assurance.

## Local specificity

`grafana` with a local mission — **or with no remote gcx context
configured** — is the local stack: apply the `setup-local-stack` skill
(isolated gcx context, datasource UIDs, ports from the global
configuration) — that skill owns the local method, this one only routes
to it, and it is fully self-serve: no user authentication to guide, so a
missing gcx setup on a fresh machine is NOT a "CLI not configured"
error. The connection proof is then `gcx config check` against the
isolated local context. A user context targeting a remote Grafana means
the run hits that remote — `grafana` names the family, the CLI's context
says which one.
