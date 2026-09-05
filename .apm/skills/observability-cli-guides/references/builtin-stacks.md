# Built-in stacks

The stacks the package knows: one row per value the MCP server's
`STACKS` whitelist accepts (`odd_config_set {"stack": ...}` rejects
anything else), with the reference file that carries everything about
it — its query surface, its `## Configuration display`, its
`## What to persist`. This table mirrors `STACKS`; a unit test in the
server's suite asserts the two agree, so adding or removing a stack
edits both in the same change.

| `STACKS` value | Reference | CLI | Where | Also called |
| --- | --- | --- | --- | --- |
| `local` | [local.md](local.md) | `gcx` (via `setup-local-stack`) | local — the default, self-serve | "the local stack", "oddyssey's stack" |
| `grafana` | [grafana.md](grafana.md) | `gcx` | remote — a Grafana the gcx context names | "my own Grafana", "Grafana Cloud", "self-hosted Grafana" |
| `azure-monitor` | [azure-monitor.md](azure-monitor.md) | `az` (KQL) | remote | "Azure", "App Insights", "Log Analytics" |
| `cloudwatch` | [cloudwatch.md](cloudwatch.md) | `aws` | remote | "AWS", "CloudWatch", "X-Ray" |
| `datadog` | [datadog.md](datadog.md) | Pup CLI (`pup`) | remote | "Datadog" |
| `dynatrace` | [dynatrace.md](dynatrace.md) | `dtctl` (DQL) | remote | "Dynatrace" |

Mapping a user's phrasing onto a value goes through the **Also called**
column; anything that maps onto no row is a custom stack when the
observed repository carries `.odd/observability-stacks/<name>.md`, and
otherwise an error naming the valid list and that location, never a
guess. `grafana` always means a **remote** Grafana — the local stack is
its own value, `local`.

The CLI column is a pointer only: the binary, its Detect command, and
its Install steps live in each reference's `## CLI binary` section
(`local.md` routes to `grafana.md`'s). A backend CLI is offered, never
installed silently — the one CLI this package installs on its own is
k6, documented in `k6-guides`.
