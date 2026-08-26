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

What it records is **what was applied and should be reapplied on the
next reset**. Environment reaches the container only at creation
(`odd_stack_up` / `odd_stack_reset` `env`), so without a written-down
copy the choice survives only as long as the container does; with one,
the next reset can be given the same env deliberately instead of from
memory. Writing it here applies nothing by itself — a `stack_config`
write never boots or resets the container.

Values are flat scalars, so the env-var values are stored as the
strings the container takes (`"true"`, `"debug"`,
`"--storage.tsdb.retention.time=90d"`). Any variable whose value is a
credential — `OTEL_EXPORTER_OTLP_HEADERS` for a dual-write to a remote
backend is the one that matters — is **not** persisted here: record the
variable name in the conversation and let the user pass its value to
`odd_stack_up`/`odd_stack_reset` directly.

## Where each value comes from

From the user's own env choices on `odd_stack_up` / `odd_stack_reset`.
There is nothing to derive and nothing to query: the container's own
environment is not the source of truth to copy back, it is the result of
what the user asked for, and the point of persisting is to keep that ask
after the container that holds it is gone. When
`odd_config_set`'s auto-reset already carried variables forward, its
`env_preserved` list names them — the names, never the values, so it
tells you what to persist, not what to write.

Host ports are **not** part of `stack_config.local`: they live in the
configuration's own `local` block (`grafana_port`, `otlp_grpc_port`,
`otlp_http_port`) and changing one resets the stack. Never fold a port
into this payload.

## What to ask the user

**Nothing**, unless the user wants persistent container env. A switch to
`local` needs no targeting information at all — the stack is on the
machine, its ports come from the configuration, and gcx is configured
against it by `setup-local-stack`. An empty or missing
`stack_config.local` is the normal state.

Ask only when the user has just made an env choice worth keeping ("turn
on Grafana's debug logs", "enable Tempo's MCP server"): confirm the
variable and value, then persist. Do not go fishing through the env
catalog for options to offer during a backend switch.
