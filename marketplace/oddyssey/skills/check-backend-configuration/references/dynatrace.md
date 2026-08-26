# Dynatrace — configuration display

## Display

The active `dtctl` context is the configuration: which environment the
DQL queries will run against.

- `dtctl auth whoami` — the authenticated identity and the environment
  URL (`https://<envid>.apps.dynatrace.com`) of the active context.
  Show the context name, the environment, and the identity; never the
  token value behind them.
- The `dynatrace.md` reference in the `observability-cli-guides` skill
  owns the CLI specifics (OAuth vs token contexts, how a context is
  created); this file owns only what to display.

`stack_config.dynatrace` is expected **empty** — the dtctl context
already names the environment. Present-and-empty (`{}`) or missing both
display as "nothing persisted — the dtctl context is the source".

Add any `invalid_ignored` dotted names as degradations: the stored
value was invalid and was dropped. `stack_config` has no defaults behind
it, so a dropped value reads as not persisted — nothing silently took
its place.

## Connection proof

`dtctl auth whoami`. It is both the context display and the cheapest
probe — one call that either returns the identity and environment
(connected) or fails. Failure = stop and guide `dtctl auth login` /
the token context setup; never run the login for the user.

## Change-request phrasing

- "change backend to dynatrace"
