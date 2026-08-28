# Local — configuration display

## Display

Every value comes from `odd_config_get`, never from a hardcoded
default: the host ports are configurable, so `3000`/`4317`/`4318` are
what a fresh machine happens to show, not what the display may assume.

- Grafana URL — `http://localhost:<local.grafana_port>`
- OTLP gRPC endpoint — `http://localhost:<local.otlp_grpc_port>`
- OTLP HTTP endpoint — `http://localhost:<local.otlp_http_port>`

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

## Connection proof

`gcx config check` against the isolated gcx context of the
`setup-local-stack` skill (`GCX_CONFIG` pointed at its per-session
file). That skill owns the method — configure through it, never against
the user's own gcx contexts. The local stack is self-serve: a missing
gcx setup is a step to run, not a "CLI not configured" error. Check the
container is up first (`odd_stack_status`) — a down stack fails the
probe for a reason no authentication guidance would fix.

## Change-request phrasing

- "set the local Grafana port to 3001"
- "change otlp_http_port to 4319"
- "clear the persisted GF_LOG_LEVEL container env"
