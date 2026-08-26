# Dynatrace — what to persist

## What stack_config holds

**Nothing.** `stack_config.dynatrace` is expected to stay empty, and an
empty entry is the correct final state of a switch to `dynatrace`.

`dtctl` is context-bearing: the active context already names the
**environment** the DQL queries run against
(`https://<envid>.apps.dynatrace.com`) and the identity behind it.
Storing the environment id or URL here would only be a stale copy of
what `dtctl auth whoami` reports first-hand, and the context is what the
query uses either way.

## Where each value comes from

From the active dtctl context, read at use time:

- `dtctl auth whoami` — the authenticated identity and the environment
  URL of the active context. One call, and it is both the display and
  the connection proof.

Whether the context is an OAuth context or a token context, the
credential lives in dtctl's own configuration; name the mechanism if it
helps the user, never the value. The `dynatrace.md` reference in the
`observability-cli-guides` skill owns how a context is created.

## What to ask the user

**Nothing about targeting.** Do not ask for the environment id, the
environment URL, or any credential.

If the user has several dtctl contexts and the active one is not the
environment they mean, the fix is a dtctl context switch, not a value in
this configuration — say so and let them run it, then re-verify.

Leave `stack_config.dynatrace` alone.
