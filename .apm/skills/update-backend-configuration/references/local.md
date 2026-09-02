# Local — what to persist

## What stack_config holds

`stack_config.local` holds the **container environment variables**
applied to the otel-lgtm container — the surface catalogued by the
`setup-local-stack` skill's `references/otel-lgtm-env.md`, which is the
container's only configuration lever. For example:

```json
{"stack_config": {"local": {"GF_LOG_LEVEL": "debug",
                            "ENABLE_LOGS_GRAFANA": "true"}}}
```

What it records is **what was applied and is reapplied on every
container creation**. `odd_stack_up` / `odd_stack_reset` maintain the
entry themselves: a creation persists the explicit env it applied
(merge), and every creation reapplies what is persisted here — explicit
entries win on collision, and the winner is what ends up stored. So the
choice survives recreations without anyone repeating it, and this entry
usually needs no manual write at all. Writing it here still applies
nothing by itself — a `stack_config` write never boots or resets the
container; the write is for corrections, and `null` clears a variable
(so the next creation stops applying it — see the skill's clearing
contract).

Values are flat scalars, so the env-var values are stored as the
strings the container takes (`"true"`, `"debug"`,
`"--storage.tsdb.retention.time=90d"`). Any variable whose value is a
credential — `OTEL_EXPORTER_OTLP_HEADERS` for a dual-write to a remote
backend is the one that matters — is **never** persisted here: the
tools exclude credential-named variables on their own (the result's
`env_not_persisted` names them) and this skill must not write one
either. Record the variable name in the conversation and let the user
pass its value to `odd_stack_up`/`odd_stack_reset` directly, at every
recreation.

## Where each value comes from

From the user's own env choices on `odd_stack_up` / `odd_stack_reset`,
which persist them automatically at creation (the result's
`env_persisted` names what was written, `env_reapplied` what came back
from here). There is nothing to derive and nothing to query — a manual
write only corrects or clears what the tools recorded.

Host ports are **not** part of `stack_config.local`: they live in the
configuration's own `local` block (`grafana_port`, `otlp_grpc_port`,
`otlp_http_port`, `pyroscope_port`) and changing one resets the stack.
Never fold a port into this payload.

## What to ask the user

**Nothing**, unless the user wants persistent container env. A switch to
`local` needs no targeting information at all — the stack is on the
machine, its ports come from the configuration, and gcx is configured
against it by `setup-local-stack`. An empty or missing
`stack_config.local` is the normal state.

Env choices need no persisting question at all — the tools record them
at creation. Ask only for a correction or a clearing the user names
("stop applying Grafana's debug logs": confirm the variable, then write
it `null`). Do not go fishing through the env catalog for options to
offer during a backend switch.
