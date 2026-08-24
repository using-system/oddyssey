# MCP Global Configuration — Design

Date: 2026-08-24
Issue: #59
Status: approved (maintainer, 2026-08-24)

## Problem

The MCP server hardcodes its entire surface: Grafana on `3000`, OTLP on
`4317`/`4318`, and agents assume the backend CLI is gcx against a local
Grafana. A machine where a port is taken cannot run the stack at all, and
nothing records which observability backend the loop currently targets —
every prompt re-derives it from mission text.

## Decisions already settled (maintainer)

- **Global, not per-project.** One shared container for every project on
  the machine is the assumed design (#50 closed not-planned); the
  configuration follows: one file, user scope, machine-wide.
- **No interactive CLI configuration.** The user configures their backend
  CLI themselves; agents verify and display (#48 closed not-planned,
  replaced by #59/#60/#61).
- **Port-change semantics: automatic reset.** Setting new ports while a
  container exists resets the stack immediately so the configuration is
  always applied — with the destruction fully visible (the embedded reset
  returns `services_wiped`, the tool description says it wipes).

## Configuration file

Path: `~/.oddyssey/config.json`. Schema, with every field optional and
defaulted:

```json
{
  "stack": "grafana",
  "local": {
    "grafana_port": 3000,
    "otlp_grpc_port": 4317,
    "otlp_http_port": 4318
  }
}
```

- `stack` — one of `grafana`, `azure-monitor`, `cloudwatch`, `datadog`,
  `dynatrace`, `splunk` (the `observability-cli-guides` backends).
  Default `grafana`, never null. There is no `local` value: local IS
  grafana, the local specificity lives in the `setup-local-stack` skill.
- `local.*_port` — the three published host ports. Defaults as today.
- Missing file = all defaults. Unknown keys are ignored on read.
- Writes are atomic (write to a temp file in the same directory, then
  rename). The file is re-read on every tool call — no in-process cache —
  so concurrent MCP servers (one per project) observe each other's
  writes; last write wins.

## New module: `app/config.py`

- `load() -> dict` — effective configuration, defaults applied. Tolerant:
  an invalid stored value (unknown stack, non-int port) falls back to the
  default for that field and the returned dict flags it
  (`"invalid_ignored": [...]`) so `odd_config_get` can surface it.
- `save(partial: dict) -> dict` — deep-merges the partial into the stored
  file and returns the new effective config. Strict validation before
  writing: `stack` must be one of the six values; ports must be ints in
  1–65535 and pairwise distinct. A rejected partial writes nothing.

## Tools

- `odd_config_get()` — the effective configuration (defaults applied),
  plus any `invalid_ignored` flags.
- `odd_config_set(config: dict)` — partial update, e.g.
  `{"stack": "datadog"}` or `{"local": {"grafana_port": 3300}}`.
  - Changing `stack` never touches the container.
  - Changing any port while a container exists (running or stopped)
    triggers `stack_reset()` after the write, so the new ports apply
    immediately; the result embeds the reset's outcome — including
    `services_wiped` — alongside the new config. With no container, the
    write alone suffices.
  - The tool description states loudly that a port change wipes all
    stored telemetry machine-wide, and that the server's own telemetry
    export honors a changed OTLP port only after the MCP server restarts.

## stack.py: ports become configuration-derived

The module constants that encode ports (`PORTS`, `PROMETHEUS_READY`,
`TEMPO_READY`, `LOKI_READY`, `PYROSCOPE_READY`, `TEMPO_SERVICE_NAMES`,
`PROMETHEUS_JOB_VALUES`, `LOKI_SERVICE_NAMES`, `GRAFANA_URL`,
`OTLP_ENDPOINT`, `OTLP_HTTP_INGEST`) become functions of the loaded
configuration, resolved at call time. `run_args()` builds its `-p`
mappings from the configured ports (host side; container side stays
3000/4317/4318).

Residual mismatch — a hand-edited config file while a container runs
(`odd_config_set` cannot leave one, the auto-reset closes that path):
`stack_up` compares the running container's actual port bindings
(`docker inspect`) with the configuration and fails immediately with a
clear message naming `odd_stack_reset`, instead of polling dead URLs for
120 s.

## telemetry.py

The server's own OTLP export default becomes
`http://localhost:<otlp_http_port>` read from the configuration **at
server startup** (the exporter is built once). A port change therefore
reaches the server's own telemetry only after the MCP server restarts —
stated in `odd_config_set`'s description. User-set `OTEL_*` variables
keep overriding everything, as today.

## Consumers

`odd_stack_up` / `odd_stack_reset` results (`grafana_url`,
`otlp_endpoint`) are the single source of truth for where the stack
lives: applications' `OTEL_EXPORTER_OTLP_ENDPOINT` and every skill
instruction must come from there or from `odd_config_get`, never from a
hardcoded port. Skill-side consumption (`setup-local-stack`,
`check-backend-configuration`) is #60; prompt-side (`odd-observe` /
`odd-verify` preflight) is #61 — both out of scope here.

## Testing

- **Unit (TDD)**: config module (defaults on missing file, tolerant
  read with `invalid_ignored`, strict save validation, deep merge,
  atomic write), tools (get shape; set triggering reset only on port
  change with a container present), `run_args` port mappings from
  config, URL derivation, `stack_up` port-mismatch detection.
- **Integration**: `odd_config_set` a non-default Grafana port → the
  embedded reset recreates the container → prove Grafana answers on the
  new port and OTLP ingests on the new port with a real request →
  restore defaults (config file and container) at the end.

## Out of scope

- Per-project isolation or per-project config (#50, not planned).
- Backend CLI authentication (#60 verifies, never authenticates).
- Prompt/agent wiring (#61).
- Container-side port remapping (only host ports are configurable).
