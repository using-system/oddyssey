# Local — the oddyssey stack on this machine

The local stack is a Grafana (LGTM) stack in one container, brought up
by `odd_stack_up`, queried with `gcx` exactly like a remote Grafana: the
query surface is [grafana.md](grafana.md) — CLI binary, output reading,
query by signal — and the ready-made isolated gcx context, the
datasource UIDs, and the push-model caveats are the `setup-local-stack`
skill's, which owns the local method end to end. This file carries what
is specific to `local` as a configured stack: how its configuration is
displayed and proven, and what `stack_config.local` persists.

## CLI binary

`gcx` — the same binary, Detect command, and Install steps as
[grafana.md](grafana.md)'s `## CLI binary`; read that section. The local
stack is fully self-serve — no account, no authentication behind it — so
a missing gcx is a step to run, never a "CLI not configured" error, and
`setup-local-stack` configures it against the stack in an isolated
context of its own.

## Setup

The method is `setup-local-stack`'s: the isolated gcx context pointed at
the configured Grafana port, the datasource UIDs, the push-model
caveats. The CLI's own setup steps are [grafana.md](grafana.md)'s
`## Setup`; nothing to authenticate here — the stack serves its API
anonymously.

## Configuration display

### Display

Every value comes from `odd_config_get`, never from a hardcoded
default: the host ports are configurable, so `3000`/`4317`/`4318`/`4040` are
what a fresh machine happens to show, not what the display may assume.

- Grafana URL — `http://localhost:<local.grafana_port>`
- OTLP gRPC endpoint — `http://localhost:<local.otlp_grpc_port>`
- OTLP HTTP endpoint — `http://localhost:<local.otlp_http_port>`
- Pyroscope ingest endpoint — `http://localhost:<local.pyroscope_port>`
  (profiles only: pyroscope-io-style SDKs push here directly, not over
  OTLP)

Then `stack_config.local`: the container environment reapplied on every
container creation (the `setup-local-stack` skill's
`references/otel-lgtm-env.md` catalogs what the image accepts) —
`odd_stack_up`/`odd_stack_reset` maintain it themselves, persisting the
env they apply and reapplying it on the next recreation.
Credential-named variables are never in it (the tools exclude them on
apply), so show the variable names always, and their values too — the
stored contract holds flat scalars and never secrets — but a name alone
is the right display for anything that still reads like a credential. A
`stack_config.local` that is present and empty (`{}`) means **not
configured**: display "no container env persisted", never an error, and
a missing key is the same statement.

Close with `invalid_ignored` when `odd_config_get` returned it: name
each dotted field and say the stored value was invalid and the shown
one is the default — a degradation the user can only fix once it is
visible.

### Connection proof

`gcx config check` against the isolated gcx context of the
`setup-local-stack` skill (`GCX_CONFIG` pointed at its per-session
file). That skill owns the method — configure through it, never against
the user's own gcx contexts. The local stack is self-serve: a missing
gcx setup is a step to run, not a "CLI not configured" error. Check the
container is up first (`odd_stack_status`) — a down stack fails the
probe for a reason no authentication guidance would fix.

### Change-request phrasing

- "set the local Grafana port to 3001"
- "change otlp_http_port to 4319"
- "clear the persisted GF_LOG_LEVEL container env"

## What to persist

### What stack_config holds

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
`env_not_persisted` names them) and the switch must not write one
either. Record the variable name in the conversation and let the user
pass its value to `odd_stack_up`/`odd_stack_reset` directly, at every
recreation.

### Where each value comes from

From the user's own env choices on `odd_stack_up` / `odd_stack_reset`,
which persist them automatically at creation (the result's
`env_persisted` names what was written, `env_reapplied` what came back
from here). There is nothing to derive and nothing to query — a manual
write only corrects or clears what the tools recorded.

Host ports are **not** part of `stack_config.local`: they live in the
configuration's own `local` block (`grafana_port`, `otlp_grpc_port`,
`otlp_http_port`, `pyroscope_port`) and changing one resets the stack.
Never fold a port into this payload.

### What to ask the user

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
