# Grafana — what to persist

## What stack_config holds

**Nothing.** `stack_config.grafana` is expected to stay empty, and an
empty entry is the correct final state of a switch to `grafana`, not an
unfinished one.

The reason is that gcx is a **context-bearing** CLI: the active context
already names the instance (`grafana.server`), the org (`org-id`) or
Cloud stack, and the default datasource UID per signal. Copying any of
that into the global configuration creates a second truth that drifts
the first time the user runs `gcx config use-context` — and the gcx
context wins for targeting regardless, so the copy would be wrong
without being consulted.

`grafana` always means a **remote** Grafana. The local stack is the
separate `local` value, with its own reference.

## Where each value comes from

From the gcx context, read at use time and never mirrored here:

- `gcx config list-contexts` — the configured contexts, active one
  marked.
- `gcx config view` — the active context's server URL, org, and
  datasource defaults.

Whichever credential the context uses (a service-account token, basic
auth, OAuth, mTLS) lives in gcx's own configuration. It is referred to
by name in any display and never written into `stack_config`.

## What to ask the user

**Nothing about targeting.** Do not ask for the instance URL, the org,
the stack id, or the datasource UIDs — asking implies they should be
stored, and they should not be.

The one thing worth raising, and only when the user has more than one
context or none active, is which gcx context the runs should use — and
the fix for that lives in gcx (`gcx config use-context <name>`), not in
this configuration. If no context points at a remote instance at all,
offer the alternative before anything else: the user may have meant the
local stack, and that is `odd_config_set {"stack": "local"}`.

Leave `stack_config.grafana` alone. If values are already stored there
from an earlier run, do not add to them and say plainly that the gcx
context is what the missions will target.
