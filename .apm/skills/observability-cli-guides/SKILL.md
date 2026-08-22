---
name: observability-cli-guides
description: Curated map of the terminal query surface of every major observability backend. Use when observing a run - local or remote - to pick the environment's backend and learn how to authenticate and query its metrics, traces, logs, and profiles from a CLI - Grafana (gcx), Datadog (Pup CLI), Dynatrace (dtctl and DQL), Azure Monitor (az), AWS CloudWatch and X-Ray (aws), Splunk (splunk CLI and SPL).
---

# Observability CLI Guides

A selection map over the query CLIs of the major observability backends.
Pick the backend of the environment you are observing, read its reference
file, then follow the linked official docs — the fetched page is the source
of truth, not memory. The method is the same everywhere: authenticate,
**discover** what the service emits, then **query** what you discovered.

## Pick the backend

| Backend | CLI | Reference |
| --- | --- | --- |
| Grafana (local oddyssey stack, self-hosted, Cloud) | `gcx` | [references/grafana.md](references/grafana.md) |
| Datadog | Pup CLI (`pup`) | [references/datadog.md](references/datadog.md) |
| Dynatrace | `dtctl` (DQL) | [references/dynatrace.md](references/dynatrace.md) |
| Azure Monitor (App Insights, Log Analytics) | `az` (KQL) | [references/azure-monitor.md](references/azure-monitor.md) |
| AWS CloudWatch + X-Ray | `aws` | [references/cloudwatch.md](references/cloudwatch.md) |
| Splunk (Enterprise / Cloud Platform, Observability Cloud) | `splunk` (SPL) | [references/splunk.md](references/splunk.md) |

Each reference covers: setup and authentication, the discovery-then-query
commands per signal (metrics, traces, logs, profiles where the backend has
them), and Planning notes with the backend's coverage gaps and quirks.

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
- If the environment's backend is not in the table, say so and fall back
  to the backend's documented REST API over `curl` — the
  discover-then-query method still applies.
