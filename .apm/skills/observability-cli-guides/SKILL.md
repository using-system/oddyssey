---
name: observability-cli-guides
description: The package's knowledge of every observability stack it supports, one reference file per stack - the terminal query surface (how to authenticate and query metrics, traces, logs, and profiles from the CLI), how the stack's configuration is displayed and proven, and what its stack_config persists - plus the list of built-in stacks. Use when observing a run, local or remote, and when backend-configuration's Check or Switch need anything about a stack - Grafana (gcx), Datadog (Pup CLI), Dynatrace (dtctl and DQL), Azure Monitor (az), AWS CloudWatch and X-Ray (aws), and the local stack.
---

# Observability CLI Guides

One reference file per stack, carrying everything the package knows about
it: the query CLI and how to set it up, the discovery-then-query commands
per signal, how its configuration is displayed and proven, and what its
`stack_config` persists. Pick the observed stack's reference, then follow
the linked official docs — the fetched page is the source of truth, not
memory. The method is the same everywhere: authenticate, **discover**
what the service emits, then **query** what you discovered.

## Pick the backend

The list of built-in stacks — every value the MCP server's `STACKS`
accepts, with its reference, CLI, and aliases — is
[references/builtin-stacks.md](references/builtin-stacks.md); it is what
`backend-configuration` (its `## Check` and `## Switch`) and
`/odd-config` read. The query surface per backend:

| Backend | CLI | Reference |
| --- | --- | --- |
| Local oddyssey stack (`local`) | `gcx` via `setup-local-stack` | [references/local.md](references/local.md), routing to grafana.md |
| Grafana (self-hosted, Cloud — `grafana`) | `gcx` | [references/grafana.md](references/grafana.md) |
| Datadog | Pup CLI (`pup`) | [references/datadog.md](references/datadog.md) |
| Dynatrace | `dtctl` (DQL) | [references/dynatrace.md](references/dynatrace.md) |
| Azure Monitor (App Insights, Log Analytics) | `az` (KQL) | [references/azure-monitor.md](references/azure-monitor.md) |
| AWS CloudWatch + X-Ray | `aws` | [references/cloudwatch.md](references/cloudwatch.md) |

Authoring a reference, or a custom stack file: every reference follows
[references/CONTRACT.md](references/CONTRACT.md) — the sections it must
carry, what each answers, and who reads it. A mission never opens it.

For the **local oddyssey stack** (the Grafana case), the `setup-local-stack`
skill carries the ready-made gcx context — isolated config and datasource
UIDs. gcx is the stack's mandatory query CLI.

## Rules

- Recommendations and commands must come from the reference's linked docs,
  fetched — never from memory; CLIs move fast.
- Credentials come from the environment or the caller (env vars, secret
  stores); never invent, echo, or store them.
- Planning notes are a snapshot (last verified 2026-08); the fetched
  official page always overrides them.
- A reference talks about its own backend only — never a comparison with
  another backend's product (routing to the local stack is not one).
- If the stack's backend is not in the table, say so and fall back to the
  backend's documented REST API over `curl` — the discover-then-query
  method still applies.
