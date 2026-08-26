# Grafana — configuration display

## Display

`grafana` is a **remote** Grafana; the gcx context is what says which
instance, so the display is the context, not an invented value.

- `gcx config list-contexts` — every configured context, with the
  active one marked.
- `gcx config view` — the active context's `grafana.server` (the
  instance the queries will hit) and its `org-id` when set. Show the
  server URL and org; never echo a token, password, or any other
  credential field the view prints.

`stack_config.grafana` is expected **empty** — the gcx context already
names the instance, and duplicating it in the global configuration only
creates a second truth to drift. Present-and-empty (`{}`) or missing
both display as "nothing persisted — the gcx context is the source".
If values are stored there anyway, show them as-is and say the gcx
context still wins for targeting.

List any `invalid_ignored` dotted names `odd_config_get` returned as
degradations: the stored value was invalid and was dropped.
`stack_config` has no defaults behind it, so a dropped value reads as
not persisted — nothing silently took its place.

## Connection proof

`gcx config check` (add `--context <name>` when proving a context other
than the active one). Success on the active context = connected. No
context configured for a remote instance is not automatically an
authentication problem: offer `odd_config_set {"stack": "local"}` first
if the user meant the local stack.

## Change-request phrasing

- "switch gcx to context <name>"
- "change backend to local"
